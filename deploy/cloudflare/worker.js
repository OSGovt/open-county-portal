// Cloudflare Worker in front of the Utopia County demonstration container.
//
// Every request goes to one shared container (so all visitors see the same
// site). The container starts on the first request, and goes to sleep after
// IDLE_MINUTES without visitors; billing stops while it sleeps, and the next
// visitor gets a freshly reset demonstration. Based on Cloudflare's official
// containers template (cloudflare/templates, containers-template).
import { DurableObject } from "cloudflare:workers";

const PORT = 8000;
const IDLE_MINUTES = 20;

export class UtopiaPortal extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    const container = ctx.container;
    if (container?.running) {
      void ctx.blockConcurrencyWhile(() => container.setInactivityTimeout(IDLE_MINUTES * 60 * 1000));
      this.observeExit();
    }
  }

  async fetch(request) {
    // Share one startup across all requests that arrive while it's starting.
    this.starting ??= this.startAndWaitForPort().finally(() => {
      this.starting = undefined;
    });
    await this.starting;

    // Keep the visitor's host name in the URL: it becomes the Host header the
    // portal sees, so redirects it builds (such as /staff -> /staff/) point at
    // utopia.osgovt.com. The container is reached through the port either way.
    const incoming = new URL(request.url);
    const url = new URL(incoming.pathname + incoming.search, `http://${incoming.host}`);
    const forwarded = new Request(url, request);
    forwarded.headers.set("x-forwarded-proto", "https");
    forwarded.headers.set("x-forwarded-host", incoming.host);
    const ip = request.headers.get("cf-connecting-ip");
    if (ip) forwarded.headers.set("x-forwarded-for", ip);
    return this.ctx.container.getTcpPort(PORT).fetch(forwarded);
  }

  async startAndWaitForPort() {
    const container = this.ctx.container;
    // A deploy restarts this Durable Object but leaves a running container on
    // the old image. Restart it when the Worker version has changed, so every
    // deploy serves the new version (and a freshly reset demo).
    const version = this.env.CF_VERSION_METADATA?.id;
    if (container.running && version && (await this.ctx.storage.get("version")) !== version) {
      console.log("New version deployed; restarting the container");
      await container.destroy("new version deployed");
    }
    if (!container.running) {
      container.start({
        image: container.images.base,
        instance: this.env.INSTANCE_TYPE || "standard-1",
        enableInternet: false,
        env: {
          PORTAL_SITE_URL: this.env.SITE_URL || "https://utopia.osgovt.com",
        },
      });
      if (version) await this.ctx.storage.put("version", version);
    }
    this.observeExit();
    await container.setInactivityTimeout(IDLE_MINUTES * 60 * 1000);

    // "running" means a start was requested; wait until the portal answers.
    const port = container.getTcpPort(PORT);
    for (let attempt = 0; attempt < 150; attempt++) {
      try {
        const response = await port.fetch("http://container/healthz", { signal: AbortSignal.timeout(1000) });
        await response.body?.cancel();
        if (response.ok) return;
      } catch {
        // Not listening yet.
      }
      await scheduler.wait(300);
    }
    throw new Error("The portal didn't become ready.");
  }

  observeExit() {
    if (this.monitoring) return;
    this.monitoring = this.ctx.container
      .monitor()
      .then(() => console.log("Container stopped"))
      .catch((error) => console.error("Container failed:", error))
      .finally(() => {
        this.monitoring = undefined;
      });
    this.ctx.waitUntil(this.monitoring);
  }
}

const WAKING = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="refresh" content="10">
<title>Utopia County is starting</title></head>
<body style="font: 18px/1.5 system-ui, sans-serif; max-width: 36rem; margin: 3rem auto; padding: 0 1rem">
<main><h1>Utopia County is starting</h1>
<p>This demonstration sleeps when nobody is using it. It's waking up now; this page tries again in 10 seconds.</p></main>
</body></html>`;

export default {
  async fetch(request, env) {
    // Plain http:// goes to https:// before anything wakes the container.
    const url = new URL(request.url);
    if (url.protocol === "http:") {
      url.protocol = "https:";
      return Response.redirect(url.toString(), 301);
    }
    try {
      return await env.PORTAL.getByName("utopia").fetch(request);
    } catch (error) {
      console.error("Request failed:", error);
      return new Response(WAKING, {
        status: 503,
        headers: { "content-type": "text/html; charset=utf-8", "retry-after": "10" },
      });
    }
  },
};
