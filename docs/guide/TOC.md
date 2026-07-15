# Table of Contents: Developer Guide

Back to [README](./README.md)

---

## By Reading Path

### 🚀 New to FastAPI (Recommended for backend engineers joining the team)
1. [System Overview](./01-system-overview.md) — Tech stack, architecture phases, scope, and design philosophy
2. [FastAPI and Layered Architecture](./02-fastapi-and-layered-architecture.md) — Request flow, dependency injection, async patterns
3. [Authentication and Security](./04-authentication-and-security.md) — JWT, bcrypt, server-side revocation
4. [Rooms, Matchmaking, and Game Engine](./05-rooms-matchmaking-and-game-engine.md) — State machines, room lifecycle, core gameplay logic
5. [Data Model and Persistence](./03-data-model-and-persistence.md) — ORM schema, relationships, design tradeoffs

### 📡 New to Redis/WebSockets (Recommended for engineers with FastAPI experience)
1. [System Overview](./01-system-overview.md) — Architectural decisions and ephemeral state concept
2. [Rooms, Matchmaking, and Game Engine](./05-rooms-matchmaking-and-game-engine.md) — Full gameplay loop with state transitions
3. [WebSocket Protocol and Real-Time Flow](./06-websocket-protocol-and-realtime-flow.md) — Event model, cross-instance fanout, message protocol
4. [Redis Strategy and Key Design](./07-redis-strategy.md) — Key design, why Redis, tradeoffs vs. alternatives
5. [Real-Time Protocol Quick Reference](./14-realtime-protocol-quick-reference.md) — Event matrix, commands, guards, close codes

### ⚡ Need to Ship Features Quickly (Recommended for feature implementers)
1. [FastAPI and Layered Architecture](./02-fastapi-and-layered-architecture.md) — How to add routes and services safely
2. [Testing and Docker Workflow](./08-testing-and-dev-workflow.md) — Docker setup, running tests locally, test patterns
3. [How to Extend This Project Safely](./09-extension-playbook.md) — Safe change patterns, backward compatibility, verification checklist
4. [Contributor Task Map](./11-contributor-task-map.md) — Map any change to files, tests, and entry points
5. [Troubleshooting Playbook](./12-troubleshooting-playbook.md) — Symptom-based debugging with Docker commands

### 🎓 New Team Member Onboarding (Recommended for first week)
1. [90-Minute Onboarding Path](./10-90-minute-onboarding-path.md) — **Start here** for a guided intro with time estimates and specific code references
2. [FastAPI and Layered Architecture](./02-fastapi-and-layered-architecture.md) — Understand the request flow
3. [Rooms, Matchmaking, and Game Engine](./05-rooms-matchmaking-and-game-engine.md) — See how the game works end-to-end
4. [WebSocket Protocol and Real-Time Flow](./06-websocket-protocol-and-realtime-flow.md) — Understand real-time communication
5. [Testing and Docker Workflow](./08-testing-and-dev-workflow.md) — Set up local development environment

### 🐛 Debugging a Production-Like Issue Locally
1. [Troubleshooting Playbook](./12-troubleshooting-playbook.md) — Symptom-based flows with Docker commands and log checks
2. [Real-Time Protocol Quick Reference](./14-realtime-protocol-quick-reference.md) — Protocol reference to understand event structure
3. [Architecture Decision Log](./13-architecture-decision-log.md) — Understand design decisions that affect debugging strategy

---

## By Topic

### Architecture & Design (Understanding the Big Picture)
- [System Overview](./01-system-overview.md) — Tech stack, phases, architectural motivation
- [FastAPI and Layered Architecture](./02-fastapi-and-layered-architecture.md) — Layered design, request flow, dependency injection
- [Architecture Decision Log](./13-architecture-decision-log.md) — 8 major decisions with tradeoffs and consequences
- [Redis Strategy and Key Design](./07-redis-strategy.md) — Redis placement, key design, why ephemeral state split

### Implementation & Patterns (How to Code Here)
- [Data Model and Persistence](./03-data-model-and-persistence.md) — ORM schema, relationships, design considerations
- [Authentication and Security](./04-authentication-and-security.md) — JWT tokens, bcrypt hashing, server-side revocation
- [Rooms, Matchmaking, and Game Engine](./05-rooms-matchmaking-and-game-engine.md) — State machines, room lifecycle, gameplay logic with sequence diagrams
- [WebSocket Protocol and Real-Time Flow](./06-websocket-protocol-and-realtime-flow.md) — Event model, cross-instance broadcast, connection lifecycle with sequence diagrams

### Operations & Development (How to Work Here)
- [Testing and Docker Workflow](./08-testing-and-dev-workflow.md) — Docker Compose setup, test strategy, fixture patterns, running tests
- [How to Extend This Project Safely](./09-extension-playbook.md) — Safe change patterns, backward compatibility, verification checklist
- [Troubleshooting Playbook](./12-troubleshooting-playbook.md) — Symptom-based debugging flows for 8+ common scenarios

### Reference & Quick-Start (Look-Up Resources)
- [90-Minute Onboarding Path](./10-90-minute-onboarding-path.md) — Guided quick-start with time estimates and file references (~1,000 lines)
- [Contributor Task Map](./11-contributor-task-map.md) — Change type → files, tests, entry points routing table (~500 lines)
- [Real-Time Protocol Quick Reference](./14-realtime-protocol-quick-reference.md) — Event matrix, command guards, error codes, close codes (~400 lines)

---

## Chapter Summaries

| Chapter | Purpose | Audience | Est. Read |
|---------|---------|----------|-----------|
| [01: System Overview](./01-system-overview.md) | Tech stack, phases, architectural decisions | All | 15 min |
| [02: FastAPI & Layered Architecture](./02-fastapi-and-layered-architecture.md) | Request flow, DI, async patterns, routing | Backend engineers | 20 min |
| [03: Data Model & Persistence](./03-data-model-and-persistence.md) | ORM schema, relationships, design tradeoffs | Backend engineers | 18 min |
| [04: Authentication & Security](./04-authentication-and-security.md) | JWT, bcrypt, server-side revocation | Backend engineers, security reviewers | 15 min |
| [05: Rooms, Matchmaking, & Game Engine](./05-rooms-matchmaking-and-game-engine.md) | State machines, room lifecycle, gameplay with diagrams | All | 30 min |
| [06: WebSocket Protocol & Real-Time Flow](./06-websocket-protocol-and-realtime-flow.md) | Event model, cross-instance fanout with diagrams | Realtime engineers | 25 min |
| [07: Redis Strategy & Key Design](./07-redis-strategy.md) | Key design, ephemeral state, tradeoffs | Backend engineers, DevOps | 20 min |
| [08: Testing & Docker Workflow](./08-testing-and-dev-workflow.md) | Docker setup, test patterns, local development | All developers | 25 min |
| [09: How to Extend Safely](./09-extension-playbook.md) | Safe change patterns, compatibility, verification | Feature implementers | 20 min |
| [10: 90-Minute Onboarding Path](./10-90-minute-onboarding-path.md) | Guided quick-start with file references | New team members | 90 min (guided) |
| [11: Contributor Task Map](./11-contributor-task-map.md) | Change type routing (auth, rooms, WebSocket, etc.) | Feature implementers, reviewers | 10 min |
| [12: Troubleshooting Playbook](./12-troubleshooting-playbook.md) | Symptom-based debugging flows | Debugging, troubleshooting | 20 min |
| [13: Architecture Decision Log](./13-architecture-decision-log.md) | 8 major design decisions with rationale | Architects, senior engineers | 25 min |
| [14: Real-Time Protocol Quick Reference](./14-realtime-protocol-quick-reference.md) | Event matrix, commands, guards, error codes | Protocol implementers, debuggers | 10 min |

---

## Navigation Shortcuts

### I want to...
- **Learn the system from scratch** → Start with chapter 1, follow "New to FastAPI" or "New to Redis/WebSockets" path
- **Add a new REST endpoint** → Chapter 2 (architecture), 9 (safe patterns), 11 (task map), 8 (testing)
- **Add a new WebSocket event** → Chapter 6, 14, 12, then 13 (why async timers?)
- **Debug a live issue** → Chapter 12 first, then 14 (protocol ref), then 13 (decisions)
- **Understand a design decision** → Chapter 13 (architecture decision log)
- **Set up my dev environment** → Chapter 8 (Docker workflow) or chapter 10 (onboarding path)
- **Understand matchmaking** → Chapter 5 with sequence diagram, then 10 or 11 for implementation entry points
- **Understand reconnections** → Chapter 6 (WebSocket flow with reconnect diagram) and 12 (troubleshooting)

---

**Last Updated:** During Phase 3 completion  
**Total Chapters:** 14  
**Estimated Total Read Time (all chapters):** ~4 hours  
**Estimated Read Time (recommended path):** ~2–2.5 hours
