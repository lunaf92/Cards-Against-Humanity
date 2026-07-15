# Developer Guide: Cards Against Humanity Clone (Backend Case Study)

This guide is for developers who already know web development, but are new to FastAPI, Redis, and WebSockets in production-style systems.

You are looking at a multiplayer backend that combines:

- REST APIs for account/card/room lifecycle
- WebSocket channels for real-time gameplay
- PostgreSQL for durable business data
- Redis for high-frequency ephemeral state
- Docker Compose as the canonical execution environment

If you read this guide, you should develop a mental model of how requests flow through the system, why data is split between PostgreSQL and Redis, how game state machines work, how to handle disconnections gracefully, and how to evolve the project safely.

## How to Use This Guide

This is a **case study guide**—designed to teach you through real code and design decisions, not abstract tutorials. Each chapter builds on prior knowledge while standing alone for reference.

Choose your path based on your goal:

- **New to FastAPI?** Start with chapters 1, 2, and 4 to understand the stack, then dive into rooms and WebSockets.
- **New to Redis/WebSockets?** Read chapters 5, 6, 7, and 14 to see how state splits between persistence layers.
- **Need to ship features?** Jump to chapters 2, 8, and 9 for patterns and extension guidelines.
- **Onboarding the team?** Start with chapter 10 for a 90-minute guided path, then fill gaps with chapters 2, 5, 6, 8.
- **Debugging in production?** Go to chapter 12 for symptom-based troubleshooting, chapter 14 for protocol reference, chapter 13 for architecture context.

For a complete chapter index with summaries and alternative organizations, see [Table of Contents](./TOC.md).

## External References

- FastAPI docs: https://fastapi.tiangolo.com/
- SQLAlchemy async docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Redis data types overview: https://redis.io/docs/latest/develop/data-types/
- WebSocket protocol overview (MDN): https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API
- Pydantic v2 docs: https://docs.pydantic.dev/latest/
