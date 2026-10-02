# Passrail: optional durable work for Bridger

You do **not** need Passrail to use Bridger interactively.

A normal Bridger setup is:

```text
your server → Bridger MCP → private tunnel / client connection → your AI
```

Add Passrail when you want work to survive individual chats or worker processes.

## What Passrail adds

Passrail provides durable local coordination for:

- scheduled or unattended work;
- producer → worker → reviewer handoffs;
- queues that survive restarts;
- claims and finite leases;
- safe retry budgets;
- explicit `UNKNOWN_OUTCOME` handling when an external action may have happened but the result is uncertain;
- durable transition and receipt evidence.

A useful mental model is:

> **Bridger gives an AI hands on a machine. Passrail gives durable work a memory.**

Passrail does not execute machine actions itself, and Bridger does not require Passrail for ordinary interactive use.

## Public Passrail project

Repository:

https://github.com/TheSpyglassofOdysseus/passrail

Easy setup:

https://github.com/TheSpyglassofOdysseus/passrail/blob/main/docs/EASY-SETUP.md

Architecture:

https://github.com/TheSpyglassofOdysseus/passrail/blob/main/docs/ARCHITECTURE.md

Threat model:

https://github.com/TheSpyglassofOdysseus/passrail/blob/main/docs/THREAT-MODEL.md

Bridger integration:

https://github.com/TheSpyglassofOdysseus/passrail/blob/main/docs/BRIDGER-INTEGRATION.md

## When to install it

Install Passrail **after** the basic Bridger path is healthy.

If your goal is simply:

> “I want my AI to operate my server while I am chatting with it.”

stop at Bridger.

If your goal becomes:

> “I want durable work to wait, be claimed, survive restarts, run later, and reconcile uncertain outcomes safely.”

then add Passrail.
