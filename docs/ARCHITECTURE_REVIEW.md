# Architecture Review

**Project:** Autonomous AI Coding Agent Platform (`sachin`)  

---

## 1. System Architecture Overview

```mermaid
graph TD
    Client[React TypeScript Frontend] -->|HTTP / REST| API[FastAPI Web Server]
    
    subgraph Backend Application Layer
        API --> Auth[Auth & Security Services]
        API --> ProjServ[Project Service]
        API --> AgentEndpoint[Sessions Endpoint]
        
        AgentEndpoint -->|Async Task| StateMachine[Agent State Machine]
        
        StateMachine --> Analyzer[Analyzer Subagent]
        StateMachine --> Planner[Planner Subagent]
        StateMachine --> Coder[Coder Subagent]
        StateMachine --> Tester[Tester Subagent]
        StateMachine --> Debugger[Debugger Subagent]
        StateMachine --> Reviewer[Reviewer Subagent]
        
        Coder --> ToolLayer[Controlled Tool Layer]
        Tester --> ToolLayer
    end
    
    subgraph Infrastructure Layer
        ToolLayer --> PathVal[Path Validator]
        ToolLayer --> Sandbox[Docker Sandbox Adapter]
        
        Auth --> Postgres[(PostgreSQL Database)]
        ProjServ --> Postgres
        
        Sandbox --> DockerContainer[Isolated Docker Containers]
        
        StateMachine --> AIProvider[AI Provider Adapter]
        AIProvider --> Anthropic[Anthropic API]
        AIProvider --> OpenAI[OpenAI API]
    end
```

---

## 2. Architectural Strengths

1. **Strict Separation of Concerns:** Domain entities (`app/domain/entities`) are completely decoupled from framework dependencies (FastAPI / SQLAlchemy).
2. **Pluggable AI Providers:** `AIProviderInterface` permits dynamic swapping between Anthropic, OpenAI, or custom LLM endpoints without altering agent loop logic.
3. **Multi-Stage Subagent Decomposition:** Complex coding tasks are split among dedicated subagents (Analyzer, Planner, Coder, Tester, Debugger, Reviewer).
4. **Isolated Execution Environment:** Untrusted code execution occurs inside ephemeral Docker containers with strict security constraints.

---

## 3. Architectural Weaknesses

1. **State Persistence Disconnect:** API endpoints use an in-memory dictionary rather than connecting `AgentStateMachine` to `AgentRepository` and PostgreSQL.
2. **Missing Real-Time Communication Layer:** Polling is used instead of WebSockets / Server-Sent Events (SSE) for streaming agent logs and execution steps.
3. **Single-Node Rate Limiter:** In-memory rate limiting impedes horizontal scaling.
