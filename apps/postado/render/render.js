#!/usr/bin/env node
/**
 * Postado Image Renderer
 * Usage: node render.js --data '<json>' --output /path/out.png [--stories]
 */
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const get = (flag) => { const i = args.indexOf(flag); return i !== -1 ? args[i + 1] : null; };

const data   = JSON.parse(get('--data'));
const output = get('--output');
const stories = args.includes('--stories');

const {
  business_name = '',
  cta = '',
  hook = '',
  hashtags = '',
  post_type = 'promo',
  brand_color = '#2d6a4f',
  image_path = null,
} = data;

// Derive a darker shade of brand_color for the panel
function hexToRgb(hex) {
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return {r,g,b};
}
function darken(hex, amt=60) {
  const {r,g,b} = hexToRgb(hex);
  return `rgb(${Math.max(0,r-amt)},${Math.max(0,g-amt)},${Math.max(0,b-amt)})`;
}
function lighten(hex, amt=40) {
  const {r,g,b} = hexToRgb(hex);
  return `rgb(${Math.min(255,r+amt)},${Math.min(255,g+amt)},${Math.min(255,b+amt)})`;
}

const panel_bg   = darken(brand_color, 80);
const accent     = brand_color;
const accent_lt  = lighten(brand_color, 60);

// Image as base64 or URL
let imgSrc = '';
if (image_path && fs.existsSync(image_path)) {
  const ext = path.extname(image_path).slice(1).toLowerCase();
  const mime = ext === 'jpg' || ext === 'jpeg' ? 'image/jpeg' : 'image/png';
  imgSrc = `data:${mime};base64,${fs.readFileSync(image_path).toString('base64')}`;
}

const W = 1080, H = stories ? 1920 : 1080;
const PHOTO_H = stories ? 1080 : 680;
const PANEL_H = H - PHOTO_H;

const postTypeLabel = {
  promo: 'PROMOÇÃO', product: 'DESTAQUE', testimonial: 'DEPOIMENTO',
  engagement: 'ENGAJAMENTO', behind_scenes: 'BASTIDORES', date: 'DATA ESPECIAL',
}[post_type] || post_type.toUpperCase();

const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700;800&display=swap');
  * { margin:0; padding:0; box-sizing:border-box; }
  body { width:${W}px; height:${H}px; overflow:hidden; font-family:'Poppins',sans-serif; background:${panel_bg}; }

  .photo-wrap {
    position: relative;
    width: ${W}px;
    height: ${PHOTO_H}px;
    overflow: hidden;
    flex-shrink: 0;
  }
  .photo {
    width: 100%; height: 100%;
    object-fit: cover;
    display: block;
  }
  .photo-top-bar {
    position: absolute;
    top: 0; left: 0; right: 0;
    padding: 28px 40px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: linear-gradient(to bottom, rgba(0,0,0,.55) 0%, transparent 100%);
  }
  .brand-pill {
    background: ${accent};
    color: #fff;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 8px 20px;
    border-radius: 100px;
  }
  .type-tag {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: rgba(255,255,255,.65);
    border: 1px solid rgba(255,255,255,.3);
    padding: 6px 16px;
    border-radius: 100px;
  }

  .panel {
    width: ${W}px;
    height: ${PANEL_H}px;
    background: ${panel_bg};
    padding: 36px 48px 30px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .divider {
    width: 48px;
    height: 3px;
    background: ${accent};
    border-radius: 2px;
    margin-bottom: 18px;
  }
  .cta-text {
    font-size: ${cta.length > 28 ? 44 : 52}px;
    font-weight: 800;
    color: #ffffff;
    line-height: 1.1;
    letter-spacing: -0.5px;
    margin-bottom: 14px;
  }
  .hook-text {
    font-size: 22px;
    font-weight: 400;
    color: rgba(255,255,255,.6);
    line-height: 1.5;
    max-width: 820px;
  }
  .footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .watermark {
    font-size: 13px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: rgba(255,255,255,.25);
    font-weight: 500;
  }
  .dot-row {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .dot { width:6px; height:6px; border-radius:50%; background: ${accent}; opacity:.5; }
  .dot.active { opacity:1; width:18px; border-radius:3px; }
</style>
</head>
<body>
  <div class="photo-wrap">
    ${imgSrc ? `<img class="photo" src="${imgSrc}">` : `<div style="width:100%;height:100%;background:${darken(brand_color,100)}"></div>`}
    <div class="photo-top-bar">
      <span class="brand-pill">${business_name}</span>
      <span class="type-tag">${postTypeLabel}</span>
    </div>
  </div>

  <div class="panel">
    <div>
      <div class="divider"></div>
      <div class="cta-text">${cta}</div>
      <div class="hook-text">${hook}</div>
    </div>
    <div class="footer">
      <span class="watermark">postado.com.br</span>
      <div class="dot-row">
        <div class="dot active"></div>
        <div class="dot"></div>
        <div class="dot"></div>
      </div>
    </div>
  </div>
</body>
</html>`;

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    headless: 'new',
  });
  const page = await browser.newPage();
  await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
  await page.setContent(html, { waitUntil: 'networkidle0' });
  await page.screenshot({ path: output, type: 'png', clip: { x: 0, y: 0, width: W, height: H } });
  await browser.close();
  process.stdout.write(JSON.stringify({ ok: true, output }));
})();
