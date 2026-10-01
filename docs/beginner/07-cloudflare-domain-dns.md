# 7. Cloudflare domain and DNS

**This chapter is optional.** A private Bridger server does not require a domain.

Use a domain when you intentionally want a stable public name for a website/API, or when your client architecture requires a public HTTPS endpoint.

## Registrar and DNS

Cloudflare Registrar documents domains sold/renewed at registry and ICANN cost without Cloudflare markup:

https://developers.cloudflare.com/registrar/

Cloudflare's prices and registry prices can change. Check both registration **and renewal** cost before purchasing.

Cloudflare also provides an API that can search, check real-time availability/pricing, and register supported domains. Registration is billable and successful registrations are non-refundable:

https://developers.cloudflare.com/registrar/registrar-api/

### Registrar tradeoff: Cloudflare nameservers are required

Cloudflare Registrar currently requires domains registered there to use Cloudflare authoritative nameservers. If you later need a different DNS provider's nameservers, you generally need to move the domain to another registrar (subject to transfer rules/locks).

Also complete registrant email verification promptly. Cloudflare documents that an unverified/expired registrant-email verification can cause an ICANN hold and disrupt normal DNS resolution.

These are manageable constraints, but they are part of the decision—not fine print to discover after purchase.

## Human approval gate

An AI may help search names and inspect current prices.

It must not call the registration endpoint or complete a purchase until the user explicitly approves:

- exact domain spelling;
- registration price;
- renewal price;
- billing account;
- auto-renew choice.

## If you already own a domain

You do not need to transfer it to Cloudflare Registrar merely to use Cloudflare DNS. Decide whether you want Cloudflare as registrar, authoritative DNS provider, both, or neither.

Changing nameservers is consequential: DNS mistakes can take websites/email offline.

## Recommended DNS pattern

Use separate names for separate trust levels.

Example:

```text
www.example.com       public website
api.example.com       explicitly public API
preview.example.com   private/Tailscale if possible
admin.example.com     private/Tailscale
```

A DNS name does not make a service safe.

## Cloudflare proxy

For supported public HTTP/HTTPS records, you may choose Cloudflare's proxy.

Do not assume an orange-cloud/proxied DNS record protects:

- SSH;
- arbitrary TCP/UDP applications;
- database ports;
- a service whose origin IP is exposed elsewhere;
- an application with no authentication.

Keep admin services private independently.

## DNSSEC

Cloudflare Registrar supports DNSSEC. Enable it when the registrar/DNS arrangement supports it, and document how it is recovered or disabled during an emergency migration.

## Domain recovery

Record privately:

- registrar;
- account email/identity;
- MFA/recovery method;
- renewal status;
- expiration date;
- authoritative nameservers;
- where DNS changes are managed.

The domain can outlive this server. Treat it as a durable asset rather than server configuration.
