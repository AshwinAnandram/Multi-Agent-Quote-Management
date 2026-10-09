from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.pricing_agent import PricingAgent
from app.agents.quoting_agent import QuotingAgent
from app.agents.research_agent import ResearchAgent
from app.agents.risk_agent import RiskAgent
from app.agents.router import AgentRouter
from app.azure_client import create_azure_openai_client
from app.config import get_required_setting
from app.services.quote_scenario_resolver import resolve_quote_scenario

class OrchestrationState(TypedDict, total=False):
    bid_id: int
    user_message: str
    router_decision: str
    selected_agents: list[str]
    execution_plan: list[str]
    completed_agents: list[str]
    agent_results: dict[str, dict]
    response: str
    quote_scenario: dict


client = create_azure_openai_client()

deployment_name = get_required_setting(
    "AZURE_OPENAI_DEPLOYMENT"
)

router = AgentRouter(
    client=client,
    deployment_name=deployment_name
)

quoting_agent = QuotingAgent(
    client=client,
    deployment_name=deployment_name
)

research_agent = ResearchAgent(
    client=client,
    deployment_name=deployment_name
)

pricing_agent = PricingAgent(
    client=client,
    deployment_name=deployment_name
)

risk_agent = RiskAgent(
    client=client,
    deployment_name=deployment_name
)

def orchestrate(
    state: OrchestrationState
) -> OrchestrationState:

    decision = router.route(
        bid_id=state["bid_id"],
        user_message=state["user_message"]
    )

    quote_scenario = resolve_quote_scenario(
        bid_id=state["bid_id"],
        user_message=state["user_message"],
        client=client,
        deployment_name=deployment_name,
    )

    if decision.decision == "CLARIFY":
        return {
            **state,
            "router_decision": "CLARIFY",
            "quote_scenario": quote_scenario,
            "selected_agents": [],
            "execution_plan": [],
            "completed_agents": [],
            "agent_results": {},
            "response": decision.clarification_question
        }

    selected_agents = decision.selected_agents

    execution_plan = [
        agent
        for agent in selected_agents
        if agent in ["research", "pricing", "risk"]
    ]

    return {
        **state,
        "router_decision": "PROCEED",
        "quote_scenario": quote_scenario,
        "selected_agents": selected_agents,
        "execution_plan": execution_plan,
        "completed_agents": [],
        "agent_results": {}
    }


def run_research(
    state: OrchestrationState
) -> OrchestrationState:

    response = research_agent.run(
        bid_id=state["bid_id"],
        user_message=state["user_message"]
    )

    agent_results = {
        **state.get("agent_results", {}),
        "research": {
            "status": "COMPLETED",
            "response": response
        }
    }

    completed_agents = [
        *state.get("completed_agents", []),
        "research"
    ]

    return {
        **state,
        "completed_agents": completed_agents,
        "agent_results": agent_results,
        "response": response
    }


def run_pricing(
    state: OrchestrationState
) -> OrchestrationState:

    response = pricing_agent.run(
        bid_id=state["bid_id"],
        user_message=state["user_message"],
        quote_scenario=state.get("quote_scenario"),
    )

    agent_results = {
        **state.get("agent_results", {}),
        "pricing": {
            "status": "COMPLETED",
            "response": response
        }
    }

    completed_agents = [
        *state.get("completed_agents", []),
        "pricing"
    ]

    return {
        **state,
        "completed_agents": completed_agents,
        "agent_results": agent_results,
        "response": response
    }



def run_risk(
    state: OrchestrationState
) -> OrchestrationState:

    quote_scenario = state.get("quote_scenario", {})
    proposed_prices = quote_scenario.get("proposed_quote_prices", [])

    prices_to_assess = proposed_prices or [None]

    risk_assessments = []

    for proposed_quote_price in prices_to_assess:
        result = risk_agent.run(
            bid_id=state["bid_id"],
            proposed_quote_price=proposed_quote_price,
        )

        risk_assessments.append(result)

    overall_risk = (
        "HIGH"
        if any(
            result["overall_risk"] == "HIGH"
            for result in risk_assessments
        )
        else "MEDIUM"
        if any(
            result["overall_risk"] == "MEDIUM"
            for result in risk_assessments
        )
        else "LOW"
    )

    risk_result = {
        "bid_id": state["bid_id"],
        "overall_risk": overall_risk,
        "assessments": risk_assessments,
    }

    agent_results = {
        **state.get("agent_results", {}),
        "risk": {
            "status": "COMPLETED",
            "response": risk_result,
        },
    }

    completed_agents = [
        agent
        for agent in state.get("completed_agents", [])
        if agent != "risk"
    ]
    completed_agents.append("risk")

    return {
        **state,
        "completed_agents": completed_agents,
        "agent_results": agent_results,
        "response": "\n\n".join(
            assessment["assessment"]
            for assessment in risk_assessments
        ),
    }


def run_quoting(
    state: OrchestrationState
) -> OrchestrationState:

    specialist_results = {
        agent_name: result
        for agent_name, result in state.get("agent_results", {}).items()
        if agent_name != "quoting"
    }

    response = quoting_agent.synthesize(
        bid_id=state["bid_id"],
        user_message=state["user_message"],
        specialist_results=specialist_results,
    )

    agent_results = {
        **specialist_results,
        "quoting": {
            "status": "COMPLETED",
            "response": response
        }
    }

    return {
        **state,
        "agent_results": agent_results,
        "response": response
    }


def route_after_orchestrator(
    state: OrchestrationState
) -> str:

    if state["router_decision"] == "CLARIFY":
        return "end"

    selected_agents = state["selected_agents"]

    if "research" in selected_agents:
        return "research_agent"

    if "pricing" in selected_agents:
        return "pricing_agent"

    if "risk" in selected_agents:
        return "risk_agent"

    return "end"


def route_after_research(
    state: OrchestrationState
) -> str:

    completed_agents = state.get(
        "completed_agents",
        []
    )

    if (
        "pricing" in state["selected_agents"]
        and "pricing" not in completed_agents
    ):
        return "pricing_agent"

    if (
        "risk" in state["selected_agents"]
        and "risk" not in completed_agents
    ):
        return "risk_agent"

    if len(state["selected_agents"]) > 1:
        return "quoting_agent"

    return "end"


def route_after_pricing(
    state: OrchestrationState
) -> str:

    completed_agents = state.get(
        "completed_agents",
        []
    )

    if (
        "research" in state["selected_agents"]
        and "research" not in completed_agents
    ):
        return "research_agent"

    if (
        "risk" in state["selected_agents"]
        and "risk" not in completed_agents
    ):
        return "risk_agent"

    if len(state["selected_agents"]) > 1:
        return "quoting_agent"

    return "end"


def route_after_risk(
    state: OrchestrationState
) -> str:

    completed_agents = state.get(
        "completed_agents",
        []
    )

    if (
        "research" in state["selected_agents"]
        and "research" not in completed_agents
    ):
        return "research_agent"

    if (
        "pricing" in state["selected_agents"]
        and "pricing" not in completed_agents
    ):
        return "pricing_agent"

    if len(state["selected_agents"]) > 1:
        return "quoting_agent"

    return "end"


def build_orchestration_graph():

    graph = StateGraph(OrchestrationState)

    graph.add_node(
        "orchestrator",
        orchestrate
    )

    graph.add_node(
        "research_agent",
        run_research
    )

    graph.add_node(
        "pricing_agent",
        run_pricing
    )

    graph.add_node(
        "risk_agent",
        run_risk
    )

    graph.add_node(
        "quoting_agent",
        run_quoting
    )

    graph.add_edge(
        START,
        "orchestrator"
    )

    graph.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "research_agent": "research_agent",
            "pricing_agent": "pricing_agent",
            "risk_agent": "risk_agent",
            "end": END
        }
    )

    graph.add_conditional_edges(
        "research_agent",
        route_after_research,
        {
            "pricing_agent": "pricing_agent",
            "risk_agent": "risk_agent",
            "quoting_agent": "quoting_agent",
            "end": END
        }
    )

    graph.add_conditional_edges(
        "pricing_agent",
        route_after_pricing,
        {
            "research_agent": "research_agent",
            "risk_agent": "risk_agent",
            "quoting_agent": "quoting_agent",
            "end": END
        }
    )

    graph.add_conditional_edges(
        "risk_agent",
        route_after_risk,
        {
            "research_agent": "research_agent",
            "pricing_agent": "pricing_agent",
            "quoting_agent": "quoting_agent",
            "end": END
        }
    )

    graph.add_edge(
        "quoting_agent",
        END
    )

    return graph.compile()