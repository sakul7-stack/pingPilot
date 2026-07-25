# PingPilot

<p align="center">
  <a href="https://ping.kushal-kc.com.np">
    <img src="static/favicon.png" alt="PingPilot" width="80">
  </a>
</p>

<p align="center">
  <a href="https://ping.kushal-kc.com.np"><strong>ping.kushal-kc.com.np</strong></a>
</p>

<p align="center">Uptime monitoring for your websites and APIs.</p>

website:  <a href="https://ping.kushal-kc.com.np"><strong>ping.kushal-kc.com.np</strong></a>
- Monitor uptime with configurable intervals
- Incident tracking
- email alerts (down & recovery)



<p align="center">
  <a href="https://ping.kushal-kc.com.np"><img src="demo1.png" alt="Dashboard" width="600"></a>
  <br><sub>Dashboard</sub>
</p>
<p align="center">
  <a href="https://ping.kushal-kc.com.np"><img src="demo2.png" alt="Monitor Detail" width="600"></a>
  <br><sub>Monitor Detail</sub>
</p>
<p align="center">
  <a href="https://ping.kushal-kc.com.np"><img src="demo3.png" alt="API Keys" width="600"></a>
  <br><sub>API Keys</sub>
</p>


## API

Read-only API authenticated via `X-API-Key` header. Manage keys at `/dashboard/api-keys/`.

| Endpoint | Description |
|---|---|
| `GET /api/monitors/` | List all monitors |
| `GET /api/monitors/<id>/` | Monitor details |
| `GET /api/monitors/<id>/heartbeats/?days=N` | Heartbeat log |
| `GET /api/monitors/<id>/incidents/` | Incidents |
| `GET /api/monitors/<id>/stats/` | Uptime stats |

