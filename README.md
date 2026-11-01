# Mercaflor — Floral Concierge

Independent touchscreen demonstration, separate from Clic Pic Mesa and the Mercaflor marketing website.

## Features
35 catalog products with original photographs and USD prices, Classic/Deluxe/Premium where applicable, English/Spanish, category navigation, cart quantities and subtotal, simulated delivery checkout and session reset after inactivity.

No backend, real orders, payment collection or confirmed delivery. Personal details stay in memory and are cleared at completion/reset or after two minutes of inactivity. Fonts load from Google Fonts. The PDF is customer-supplied; images and brand assets are not offered under an open-source license.

## Development
Node 24. Run `npm ci`, then `npm run dev`. Production: `npm run build`; output is `dist/`.

## Source of truth
`src/catalog.json` maps 35 products to original PDF pages. Original: `public/floral-concierge-2027.pdf`. Photographs extracted from the PDF without generative alteration. Verify any future catalog changes against the source.

## Hosting
Target: https://mercaflor.clicpic.co
See DEPLOY.md. This repository does not deploy the marketing landing page.
