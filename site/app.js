// Gunshot landing page: live GitHub releases + in-browser sound previews.
// No framework, no build step, no tracking.

const REPO = "Rohit-3D2Y/gunshot-keyboard";
const RELEASES_PAGE = `https://github.com/${REPO}/releases/latest`;

const PACK_BLURBS = {
  "Gunshot": "The original. Bang.",
  "Yamete Kudasai": "Ya-me-te-ku-da-sa-i, one syllable per key",
  "Moan": "Human sighs and moans",
  "Zombie": "Braaains",
  "Cat": "Five different meows",
  "Duck": "Quacks and a rubber duck",
  "Fart": "You know what this is",
  "Laser": "Sci-fi pew-pew",
  "Punch": "Every key lands a hit",
  "Mechanical Keyboard": "Real Cherry MX Blues, clicky",
  "Thocky Keyboard": "Linear switches, deep thock",
  "IBM Model M": "1986 buckling springs",
  "Typewriter": "With a bell on Enter",
};

// --- downloads -----------------------------------------------------------

function detectOS() {
  const ua = navigator.userAgent;
  const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
  if (/Win/i.test(platform) || /Windows/i.test(ua)) return "windows";
  if (/Mac/i.test(platform) || /Mac OS X/i.test(ua)) return "mac";
  return "other";
}

async function detectMacArch() {
  // Chromium can tell us; Safari can't, and almost all Macs sold since 2021 are Apple Silicon.
  try {
    if (navigator.userAgentData && navigator.userAgentData.getHighEntropyValues) {
      const { architecture } = await navigator.userAgentData.getHighEntropyValues(["architecture"]);
      if (architecture === "x86") return "x86_64";
    }
  } catch (_) { /* ignore */ }
  return "arm64";
}

function classify(assets) {
  const find = (re) => assets.find((a) => re.test(a.name));
  return {
    windows: find(/Setup.*\.exe$/i),
    macArm: find(/macos-arm64\.dmg$/i),
    macIntel: find(/macos-x86_64\.dmg$/i),
    sums: find(/SHA256SUMS/i),
  };
}

const mb = (bytes) => `${(bytes / 1048576).toFixed(0)} MB`;

async function fetchReleases() {
  const cacheKey = "gunshot-releases";
  const cached = sessionStorage.getItem(cacheKey);
  if (cached) {
    const { at, data } = JSON.parse(cached);
    if (Date.now() - at < 10 * 60 * 1000) return data;
  }
  const res = await fetch(`https://api.github.com/repos/${REPO}/releases?per_page=10`, {
    headers: { Accept: "application/vnd.github+json" },
  });
  if (!res.ok) throw new Error(`GitHub API ${res.status}`);
  const data = (await res.json()).filter((r) => !r.draft);
  sessionStorage.setItem(cacheKey, JSON.stringify({ at: Date.now(), data }));
  return data;
}

async function setupDownloads(releases) {
  const latest = releases.find((r) => !r.prerelease);
  if (!latest) return;
  const a = classify(latest.assets);
  const os = detectOS();
  const primary = document.getElementById("dl-primary");
  const label = document.getElementById("dl-label");
  const meta = document.getElementById("dl-meta");
  const others = document.getElementById("dl-others");
  const version = latest.tag_name.replace(/^v/, "");

  let main = null;
  const links = [];
  if (a.windows) links.push({ key: "windows", text: "Windows", asset: a.windows });
  if (a.macArm) links.push({ key: "macArm", text: "macOS (Apple Silicon)", asset: a.macArm });
  if (a.macIntel) links.push({ key: "macIntel", text: "macOS (Intel)", asset: a.macIntel });

  if (os === "windows") main = links.find((l) => l.key === "windows");
  if (os === "mac") {
    const arch = await detectMacArch();
    main = links.find((l) => l.key === (arch === "x86_64" ? "macIntel" : "macArm"));
  }

  if (main) {
    primary.href = main.asset.browser_download_url;
    label.textContent = `Download for ${main.text}`;
    meta.textContent = `v${version} · ${mb(main.asset.size)} · Free`;
  } else {
    primary.href = RELEASES_PAGE;
    label.textContent = "Download for Windows or Mac";
    meta.textContent = `v${version} · Free`;
  }
  others.innerHTML = "";
  for (const l of links) {
    if (l === main) continue;
    const link = document.createElement("a");
    link.href = l.asset.browser_download_url;
    link.textContent = `${l.text} (${mb(l.asset.size)})`;
    others.appendChild(link);
  }
  const all = document.createElement("a");
  all.href = latest.html_url;
  all.textContent = "All files & checksums";
  others.appendChild(all);

  document.getElementById("version-line").textContent =
    `Version ${version} · Free and open source (MIT) · No tracking · No internet connection`;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Just enough Markdown for GitHub's release notes: headings, bullets, links, bold.
function renderNotes(md) {
  const inline = (t) =>
    escapeHtml(t)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/(^|\s)(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  let html = "";
  let inList = false;
  for (const raw of (md || "").split(/\r?\n/)) {
    const line = raw.trim();
    const bullet = line.match(/^[*-]\s+(.*)/);
    if (bullet) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(bullet[1])}</li>`;
      continue;
    }
    if (inList) { html += "</ul>"; inList = false; }
    if (!line) continue;
    const heading = line.match(/^#{1,6}\s+(.*)/);
    html += heading ? `<p><strong>${inline(heading[1])}</strong></p>` : `<p>${inline(line)}</p>`;
  }
  if (inList) html += "</ul>";
  return html;
}

function renderReleases(releases) {
  const list = document.getElementById("release-list");
  if (!releases.length) {
    list.innerHTML = '<p class="muted">No releases yet. Check back soon.</p>';
    return;
  }
  const latestId = (releases.find((r) => !r.prerelease) || {}).id;
  list.innerHTML = "";
  for (const r of releases.slice(0, 6)) {
    const a = classify(r.assets);
    const el = document.createElement("article");
    el.className = "release";
    const date = new Date(r.published_at || r.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
    const badge = r.id === latestId ? '<span class="tag">Latest</span>' : r.prerelease ? '<span class="tag">Pre-release</span>' : "";
    const assetLinks = [
      a.windows && `<a href="${a.windows.browser_download_url}">Windows</a>`,
      a.macArm && `<a href="${a.macArm.browser_download_url}">macOS Apple Silicon</a>`,
      a.macIntel && `<a href="${a.macIntel.browser_download_url}">macOS Intel</a>`,
      a.sums && `<a href="${a.sums.browser_download_url}">SHA256SUMS</a>`,
    ].filter(Boolean).join("");
    el.innerHTML = `
      <header><h3>${escapeHtml(r.name || r.tag_name)}${badge}</h3><time>${date}</time></header>
      <div class="notes">${renderNotes(r.body)}</div>
      <div class="assets">${assetLinks}<a href="${r.html_url}" target="_blank" rel="noopener">View on GitHub</a></div>`;
    list.appendChild(el);
  }
}

// --- sounds ----------------------------------------------------------------

let ctx = null;
let master = null;
let packs = [];
let current = null;
const buffers = new Map(); // url -> AudioBuffer
let seqIndex = -1;
let seqLast = 0;
let lastClip = -1;
let shots = 0;

function audio() {
  if (!ctx) {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    master = ctx.createGain();
    master.gain.value = Number(document.getElementById("volume").value);
    master.connect(ctx.destination);
  }
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

async function load(url) {
  if (buffers.has(url)) return buffers.get(url);
  const promise = fetch(url).then((r) => r.arrayBuffer()).then((b) => audio().decodeAudioData(b));
  buffers.set(url, promise);
  return promise;
}

function preload(pack) {
  for (const url of [...pack.clips, ...Object.values(pack.special)]) load(url);
}

function pickClip(pack, key) {
  if (key && pack.special[key]) return pack.special[key];
  const n = pack.clips.length;
  if (pack.sequential) {
    const now = performance.now();
    if (now - seqLast > 2000) seqIndex = -1;
    seqLast = now;
    seqIndex = (seqIndex + 1) % n;
    return pack.clips[seqIndex];
  }
  let i = Math.floor(Math.random() * n);
  if (n > 1 && i === lastClip) i = (i + 1) % n;
  lastClip = i;
  return pack.clips[i];
}

async function play(pack, key) {
  const buffer = await load(pickClip(pack, key));
  const src = audio().createBufferSource();
  src.buffer = buffer;
  src.connect(master);
  src.start();
}

function selectPack(slug) {
  current = packs.find((p) => p.slug === slug) || packs[0];
  seqIndex = -1;
  for (const chip of document.querySelectorAll(".chip")) {
    chip.setAttribute("aria-checked", String(chip.dataset.slug === current.slug));
  }
  preload(current);
}

function setupSounds() {
  const chips = document.getElementById("pack-chips");
  const grid = document.getElementById("pack-grid");
  for (const pack of packs) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.dataset.slug = pack.slug;
    chip.setAttribute("role", "radio");
    chip.textContent = pack.name;
    chip.addEventListener("click", () => {
      selectPack(pack.slug);
      play(pack);
      document.getElementById("try-box").focus();
    });
    chips.appendChild(chip);

    const card = document.createElement("button");
    card.className = "card";
    card.innerHTML = `<span class="play">▶</span><span><strong>${escapeHtml(pack.name)}</strong><span class="desc">${escapeHtml(PACK_BLURBS[pack.name] || "")}</span></span>`;
    card.addEventListener("click", async () => {
      selectPack(pack.slug);
      card.classList.add("playing");
      // A short burst, like typing a word.
      const count = pack.sequential ? pack.clips.length : 5;
      for (let i = 0; i < count; i++) {
        play(pack);
        await new Promise((r) => setTimeout(r, pack.sequential ? 220 : 130));
      }
      if (pack.special.enter) { await new Promise((r) => setTimeout(r, 200)); play(pack, "enter"); }
      setTimeout(() => card.classList.remove("playing"), 300);
    });
    grid.appendChild(card);
  }
  selectPack("gunshot");

  const box = document.getElementById("try-box");
  const counter = document.getElementById("key-count");
  const special = { Enter: "enter", " ": "space", Backspace: "backspace" };
  box.addEventListener("keydown", (e) => {
    if (e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
    play(current, special[e.key]);
    shots += 1;
    counter.textContent = `${shots} ${shots === 1 ? "shot" : "shots"} fired`;
  });
  box.addEventListener("focus", () => audio());
  document.getElementById("volume").addEventListener("input", (e) => {
    audio();
    master.gain.value = Number(e.target.value);
  });
}

// --- install tabs ----------------------------------------------------------

function setupTabs() {
  const show = (name) => {
    for (const t of document.querySelectorAll(".tab")) t.classList.toggle("active", t.dataset.tab === name);
    for (const p of document.querySelectorAll("[data-panel]")) p.classList.toggle("hidden", p.dataset.panel !== name);
  };
  for (const t of document.querySelectorAll(".tab")) t.addEventListener("click", () => show(t.dataset.tab));
  if (detectOS() === "mac") show("mac");
}

// --- boot ------------------------------------------------------------------

setupTabs();

fetch("/sounds/packs.json")
  .then((r) => r.json())
  .then((data) => { packs = data; setupSounds(); })
  .catch(() => { document.getElementById("try").hidden = true; });

fetchReleases()
  .then((releases) => { setupDownloads(releases); renderReleases(releases); })
  .catch(() => {
    document.getElementById("release-list").innerHTML =
      `<p class="muted">Couldn't load releases right now. <a href="https://github.com/${REPO}/releases">See them on GitHub</a>.</p>`;
  });
