from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field


AgentName = Literal[
    "research",
    "pricing",
    "risk",
]


class RouterDecision(BaseModel):
    decision: Literal[
        "PROCEED",
        "CLARIFY",
    ]

    selected_agents: list[AgentName] = Field(
        default_factory=list,
        description=(
            "The specialist agents required to handle "
            "the user's request."
        ),
    )

    clarification_question: str | None = Field(
        default=None,
        description=(
            "A concise clarification question to ask the "
            "sales representative when the request is ambiguous."
        ),
    )


class AgentRouter:

    def __init__(
        self,
        client: OpenAI,
        deployment_name: str
    ):
        self.client = client
        self.deployment_name = deployment_name

    def route(
        self,
        bid_id: int,
        user_message: str
    ) -> RouterDecision:

        system_prompt = """
                            You are the routing component of an enterprise
                            quote management system.

                            Your job is to determine which specialist capabilities
                            are required to answer a sales representative's request.

                            Available specialist agents:

                            1. research

                            Handles:
                            - Customer history
                            - Previous bids
                            - Previous wins
                            - Previous losses
                            - Historical win rates
                            - Customer performance
                            - Historical deal information

                            2. pricing

                            Handles:
                            - Quote price simulation
                            - Price comparison
                            - Pricing optimization
                            - Margin and discount constraints
                            - Win probability at a proposed price
                            - Expected profit

                            3. risk

                            Handles:
                            - Deal risk
                            - Customer risk
                            - Competitive risk
                            - Factors that could affect the likelihood
                              of winning the deal

                            You must make one of two decisions:

                            PROCEED
                            Use PROCEED when the user's request is sufficiently
                            specific to determine which specialist capabilities
                            are required.

                            CLARIFY
                            Use CLARIFY when the user's request is ambiguous,
                            too vague, or does not provide enough information
                            to determine which specialist capability is needed.

                            Rules:

                            - Select one or more specialist agents when the
                              decision is PROCEED.
                            - You may select multiple agents when the request
                              requires multiple capabilities.
                            - Select the minimum set of specialist agents required
                              to answer the request.
                            - Do not select an agent merely because its subject
                              is mentioned incidentally.
                            - Do not determine execution order.
                            - Do not generate the answer to the user's request.
                            - Do not calculate pricing or risk metrics.
                            - Do not retrieve data.
                            - Do not invoke any specialist agent.
                            - Only return the structured routing decision.

                            When the decision is PROCEED:

                            - selected_agents must contain at least one agent.
                            - clarification_question must be null.

                            When the decision is CLARIFY:

                            - selected_agents must be an empty list.
                            - clarification_question must contain a useful question
                              that helps the sales representative clarify their intent.
                            - The clarification question should guide the user toward
                              the capabilities supported by the system.

                            Examples:

                            User:
                            "What is this customer's historical win rate?"

                            Decision:
                            PROCEED

                            Agents:
                            research

                            User:
                            "What happens if I quote $95000?"

                            Decision:
                            PROCEED

                            Agents:
                            pricing

                            User:
                            "What is the optimal price?"

                            Decision:
                            PROCEED

                            Agents:
                            pricing

                            User:
                            "What are the risks associated with this deal?"

                            Decision:
                            PROCEED

                            Agents:
                            risk

                            User:
                            "What is the customer's win history and what price
                            should I quote?"

                            Decision:
                            PROCEED

                            Agents:
                            research, pricing

                            User:
                            "Review the customer's history, assess the deal risk,
                            and recommend a price."

                            Decision:
                            PROCEED

                            Agents:
                            research, risk, pricing

                            User:
                            "What should I do?"

                            Decision:
                            CLARIFY

                            Clarification:
                            "Could you clarify what you'd like help with? I can
                            review the customer's history, evaluate deal risk,
                            or analyze the quote price."

                            User:
                            "Help me with this bid."

                            Decision:
                            CLARIFY

                            User:
                            "Can you take a look at this?"

                            Decision:
                            CLARIFY
                        """

        response = self.client.responses.parse(
            model=self.deployment_name,
            instructions=system_prompt,
            input=(
                f"Bid ID: {bid_id}\n\n"
                f"Sales representative request:\n"
                f"{user_message}"
            ),
            text_format=RouterDecision,
        )

        decision = response.output_parsed

        if decision is None:
            raise RuntimeError(
                "The router did not return a valid routing decision."
            )

        if decision.decision == "PROCEED":

            if not decision.selected_agents:
                raise RuntimeError(
                    "Router returned PROCEED without selecting "
                    "any specialist agents."
                )

            if decision.clarification_question is not None:
                raise RuntimeError(
                    "Router returned PROCEED with a "
                    "clarification question."
                )

        if decision.decision == "CLARIFY":

            if decision.selected_agents:
                raise RuntimeError(
                    "Router returned CLARIFY while selecting "
                    "specialist agents."
                )

            if not decision.clarification_question:
                raise RuntimeError(
                    "Router returned CLARIFY without a "
                    "clarification question."
                )

        return decision