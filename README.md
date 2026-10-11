# Multi-Agent Quote Management

An AI-assisted quote and bid management platform designed to help teams
process customer requests for quotation (RFQs), evaluate pricing
options, and prepare data-informed bid recommendations.

The project combines a multi-agent architecture with application
services and database-backed commercial rules. Its goal is to automate
repetitive RFQ work while keeping pricing acceptance deterministic.

## Why this project?

Responding to an RFQ can require extracting requirements from incoming
requests, structuring line items, reviewing historical bid outcomes,
comparing prices, assessing deal risk, and checking the proposed quote
against the applicable pricing policy.

This project brings these activities into a common workflow so sales and
pricing teams can reduce manual processing and make decisions with
clearer evidence.

## Intended workflow

1.  **Receive and structure an RFQ** --- capture the request and its
    commercial requirements in a structured form.
2.  **Build the bid context** --- retrieve relevant bid, quote,
    customer, and pricing information available to the application.
3.  **Evaluate pricing options** --- simulate candidate prices and
    optimize within applicable pricing constraints.
4.  **Assess risk** --- use risk rules and supporting evidence to
    classify deal risk separately from commercial acceptance.
5.  **Synthesize a recommendation** --- combine specialist outputs into
    an understandable recommendation.
6.  **Apply a quote** --- validate the proposed price against the
    applicable policy before creating a new quote version.

The availability of individual integrations and workflow steps depends
on the current application configuration and implementation.

## Key business rule: pricing policy is authoritative

A quote must comply with the applicable database-configured pricing
policy. A language model, recommendation, or risk classification must
not override this rule.

The current policy model includes:

-   `min_margin_pct` --- minimum acceptable margin percentage.
-   `max_discount_pct` --- maximum acceptable discount percentage.
-   `customer_id` --- optional customer-specific policy scope.
-   `is_active` --- whether a policy is active.

The policy lookup uses an active customer-specific policy when one is
available and otherwise falls back to the active global policy.

The live database configuration verified during development contained
the following values:

  Policy scope        Minimum margin   Maximum discount
  ----------------- ---------------- ------------------
  Global fallback                35%                25%
  Customer ID 12                 30%                30%

These are the values observed during development, not immutable
defaults. The database is the source of truth; values may differ in
another environment.

**Commercial acceptance and risk classification are separate concerns.**
Risk rules help describe a deal's risk; they do not permit a quote that
violates the applicable margin or discount limits.

## Architecture at a glance

The repository is organized around the `rfq_agent/` application:

-   **Application API and services** --- coordinate quote simulation,
    optimization, policy lookup, and quote application.
-   **Agents** --- coordinate specialist work such as pricing, risk
    assessment, and recommendation synthesis.
-   **Repositories and database access** --- retrieve bid and policy
    data and persist quote versions.
-   **Machine-learning components** --- support pricing-related
    analysis.
-   **Frontend** --- provides the user-facing application.
-   **Notebooks** --- support experimentation and analysis.
-   **Tests** --- contain automated checks for application behavior.

Relevant implementation areas include `rfq_agent/app/agents/`,
`rfq_agent/app/services/`, `rfq_agent/app/repositories/`,
`rfq_agent/app/api/`, `rfq_agent/ml/`, `rfq_agent/frontend/`, and
`rfq_agent/tests/`.

## Repository layout

``` text
.
├── .gitignore
└── rfq_agent/
    ├── app/
    │   ├── agents/
    │   ├── api/
    │   ├── repositories/
    │   └── services/
    ├── frontend/
    ├── ml/
    ├── notebooks/
    ├── tests/
    └── Deal Risk Table.xlsx
```

This is a high-level view of the main areas; individual files may change
as development continues.

## Technology

The repository is primarily Python-based and includes a frontend,
database-backed services, agent orchestration, and machine-learning
components. PostgreSQL is used for application data and pricing
policies.

Use the current project configuration as the source of truth for
dependency versions, model-provider settings, environment variables, and
runtime commands.

## Getting started

### 1. Clone the repository

``` bash
git clone https://github.com/AshwinAnandram/Multi-Agent-Quote-Management.git
cd Multi-Agent-Quote-Management
```

### 2. Review application configuration

The application lives in `rfq_agent/`. Before running it:

-   Review the dependency and project configuration files in that
    directory.
-   Configure the required database connection and model-provider
    credentials in your local environment.
-   Keep secrets in local environment files or a secrets manager. Do not
    commit API keys, database passwords, or other credentials.
-   Confirm that the database has the required tables and pricing-policy
    records.

### 3. Run and test

Use the run and test commands defined by the current project
configuration. Automated tests are located in `rfq_agent/tests/`.

This README intentionally does not prescribe unverified startup commands
or environment-variable names.

## Development principles

-   **Policy before persuasion:** commercial acceptance rules are
    enforced by application logic, not LLM-generated text.
-   **Database-backed configuration:** thresholds come from the active
    policy selected for the bid's customer.
-   **Separate risk from eligibility:** a risk score or category does
    not override pricing-policy compliance.
-   **Consistent enforcement:** simulation, comparison, optimization,
    and quote application should agree on whether a price is compliant.
-   **Evidence-led changes:** verify database schema, records, and
    configuration before changing policy behavior.
-   **Minimal, tested changes:** preserve the existing architecture and
    add tests for business-rule changes.

## Testing priorities

When changing pricing or quote behavior, tests should cover:

-   A quote that satisfies both margin and discount limits.
-   A quote below the minimum margin.
-   A quote above the maximum discount.
-   Selection of an active customer-specific policy.
-   Fallback to the active global policy when no applicable
    customer-specific policy is available.
-   Consistent results across simulation, candidate-price comparison,
    optimization, and quote application.
-   Prevention of quote-version creation when a proposed price is
    rejected.

These are testing priorities, not a claim that every scenario is already
covered by the current test suite.

## Project status

This is an actively developed project. Features, integrations, and setup
instructions may evolve. Consult the code and current configuration for
the implemented behavior of a particular environment.

## Security

-   Never commit `.env` files, API keys, access tokens, database
    credentials, or customer-sensitive RFQ data.
-   Use synthetic or appropriately anonymized data for development and
    testing.
-   Apply least-privilege access to databases and external services.
-   Avoid exposing confidential commercial information in logs and error
    messages.

## License

No license is currently specified in this repository. Unless a license
is added, reuse and redistribution are not automatically granted.
