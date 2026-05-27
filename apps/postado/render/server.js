/**
 * Postado Render Server
 * POST /render  { data: {...}, image_b64: "..." }  → PNG bytes
 * Run: node server.js  (port 9191)
 */
const express = require('express');
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');

const app = express();
app.use(express.json({ limit: '20mb' }));

const PORT = 9191;
const CHROME = '/usr/bin/google-chrome';

function darken(hex, amt = 80) {
  const r = Math.max(0, parseInt(hex.slice(1,3),16) - amt);
  const g = Math.max(0, parseInt(hex.slice(3,5),16) - amt);
  const b = Math.max(0, parseInt(hex.slice(5,7),16) - amt);
  return `rgb(${r},${g},${b})`;
}
function lighten(hex, amt = 60) {
  const r = Math.min(255, parseInt(hex.slice(1,3),16) + amt);
  const g = Math.min(255, parseInt(hex.slice(3,5),16) + amt);
  const b = Math.min(255, parseInt(hex.slice(5,7),16) + amt);
  return `rgb(${r},${g},${b})`;
}

function buildHtml({ business_name='', cta='', hook='', post_type='promo', brand_color='#2d6a4f', imgSrc='', stories=false }) {
  const W = 1080, H = stories ? 1920 : 1080;
  const PHOTO_H = stories ? 1080 : 690;
  const PANEL_H = H - PHOTO_H;
  const panel_bg = darken(brand_color, 100);
  const accent = brand_color;
  const typeLabels = {
    promo:'PROMOÇÃO', product:'DESTAQUE', testimonial:'DEPOIMENTO',
    engagement:'ENGAJAMENTO', behind_scenes:'BASTIDORES', date:'DATA ESPECIAL',
  };
  const typeLabel = typeLabels[post_type] || post_type.toUpperCase();
  const ctaSize = cta.length > 32 ? 42 : cta.length > 24 ? 48 : 54;

  return `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{width:${W}px;height:${H}px;overflow:hidden;font-family:'Poppins',sans-serif;background:${panel_bg}}
.photo-wrap{position:relative;width:${W}px;height:${PHOTO_H}px;overflow:hidden;flex-shrink:0}
.photo{width:100%;height:100%;object-fit:cover;display:block}
.photo-top{position:absolute;top:0;left:0;right:0;padding:32px 44px;display:flex;align-items:center;justify-content:space-between;background:linear-gradient(to bottom,rgba(0,0,0,.6) 0%,transparent 100%)}
.brand-pill{background:${accent};color:#fff;font-size:16px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;padding:10px 24px;border-radius:100px;white-space:nowrap;max-width:540px;overflow:hidden;text-overflow:ellipsis}
.type-tag{font-size:12px;font-weight:600;letter-spacing:3px;text-transform:uppercase;color:rgba(255,255,255,.7);border:1px solid rgba(255,255,255,.35);padding:7px 18px;border-radius:100px;white-space:nowrap}
.panel{width:${W}px;height:${PANEL_H}px;background:${panel_bg};padding:38px 48px 32px;display:flex;flex-direction:column;justify-content:space-between}
.accent-line{width:52px;height:4px;background:${accent};border-radius:2px;margin-bottom:20px}
.cta{font-size:${ctaSize}px;font-weight:800;color:#fff;line-height:1.1;letter-spacing:-.5px;margin-bottom:16px}
.hook{font-size:22px;font-weight:400;color:rgba(255,255,255,.58);line-height:1.55;max-width:840px}
.footer{display:flex;align-items:center;justify-content:space-between}
.watermark{font-size:13px;letter-spacing:3px;text-transform:uppercase;color:rgba(255,255,255,.2);font-weight:500}
.dots{display:flex;gap:7px;align-items:center}
.dot{width:7px;height:7px;border-radius:50%;background:${accent};opacity:.4}
.dot.on{opacity:1;width:20px;border-radius:4px}
</style></head>
<body>
<div class="photo-wrap">
  ${imgSrc ? `<img class="photo" src="${imgSrc}">` : `<div style="width:100%;height:100%;background:${darken(brand_color,130)}"></div>`}
  <div class="photo-top">
    <span class="brand-pill">${business_name}</span>
    <span class="type-tag">${typeLabel}</span>
  </div>
</div>
<div class="panel">
  <div>
    <div class="accent-line"></div>
    <div class="cta">${cta}</div>
    <div class="hook">${hook}</div>
  </div>
  <div class="footer">
    <span class="watermark">postado.com.br</span>
    <div class="dots"><div class="dot on"></div><div class="dot"></div><div class="dot"></div></div>
  </div>
</div>
</body></html>`;
}

let browser;
async function getBrowser() {
  if (!browser || !browser.connected) {
    browser = await puppeteer.launch({
      executablePath: CHROME,
      args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--disable-gpu'],
      headless: 'new',
    });
  }
  return browser;
}

app.post('/render', async (req, res) => {
  const { data = {}, image_b64 = '', stories = false } = req.body;
  let imgSrc = '';

  // Write temp image if provided
  let tmpFile = null;
  if (image_b64) {
    imgSrc = `data:image/jpeg;base64,${image_b64}`;
  }

  try {
    const W = 1080, H = stories ? 1920 : 1080;
    const html = buildHtml({ ...data, imgSrc, stories });
    const b = await getBrowser();
    const page = await b.newPage();
    await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
    await page.setContent(html, { waitUntil: 'networkidle0' });
    const png = await page.screenshot({ type: 'png', clip: { x:0, y:0, width:W, height:H } });
    await page.close();
    res.set('Content-Type', 'image/png').send(png);
  } catch (e) {
    console.error('Render error:', e.message);
    res.status(500).json({ error: e.message });
  } finally {
    // no temp files needed anymore
  }
});

app.get('/health', (_req, res) => res.json({ ok: true }));

app.listen(PORT, '0.0.0.0', () => console.log(`Postado render server on :${PORT}`));
process.on('SIGTERM', async () => { if (browser) await browser.close(); process.exit(0); });
