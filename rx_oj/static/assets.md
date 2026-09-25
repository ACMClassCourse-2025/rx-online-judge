# Local design assets

Typography and colors follow the [Rust website](https://rust-lang.org/).
All fonts and illustrations are served locally; the UI makes no third-party requests.

- `fonts/alfa-slab-one-latin.woff2`: Alfa Slab One Regular, from the Rust website.
  Copyright and SIL Open Font License: `fonts/AlfaSlabOne-OFL.txt`.
- `fonts/fira-sans-*-latin.woff2`: Fira Sans Regular, SemiBold, and ExtraBold,
  from the Rust website. Copyright and SIL Open Font License: `fonts/FiraSans-OFL.txt`.
- `images/fellis.svg`: the happy Ferris illustration by Karen Rustad Tölva,
  from <https://rustacean.net/assets/rustacean-flat-happy.svg>.
  Released under [CC0](https://creativecommons.org/publicdomain/zero/1.0/),
  as recorded at <https://rustacean.net/>. Called Fellis in this judge.
  The front-page SVG in `index.html` reuses the body and eye paths with custom
  articulated claws, moving eye highlights, and an impact spark. Its clap is based on
  the [Ferris clapping loop](https://tenor.com/view/ferris-crab-cheer-clap-looping-gif-26403768)
  (five claps in 1.7 seconds). The GIF itself is not bundled or loaded by the page.
- The run page in `run.js` reuses that CC0 Ferris body with articulated claws and
  additional feet. Its skateboard, coastal scenery, woodland, mountains, and night
  sky are local SVG artwork. CSS animates the scene without external assets.
