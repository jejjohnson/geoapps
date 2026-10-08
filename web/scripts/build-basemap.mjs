// Builds the offline basemap in public/basemap/ from Natural Earth (public domain)
// and Noto Sans glyphs (SIL Open Font License, via protomaps/basemaps-assets).
//
//   node scripts/build-basemap.mjs            # downloads, filters and simplifies
//
// The output is committed, so the app works offline without running this.
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson";
const GLYPHS = "https://raw.githubusercontent.com/protomaps/basemaps-assets/main/fonts";
const OUT = new URL("../public/basemap/", import.meta.url).pathname;
const CACHE = process.env.NE_CACHE ?? join(OUT, "..", "..", ".ne-cache");
const FONTS = ["Noto Sans Regular", "Noto Sans Medium", "Noto Sans Italic"];
const RANGES = ["0-255", "256-511"]; // Latin and Latin Extended-A; labels use ASCII names

mkdirSync(OUT, { recursive: true });
mkdirSync(CACHE, { recursive: true });

async function fetchTo(url, path) {
  if (existsSync(path)) return path;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  writeFileSync(path, Buffer.from(await res.arrayBuffer()));
  return path;
}

const ne = async (name) => fetchTo(`${NE}/${name}.geojson`, join(CACHE, `${name}.geojson`));

function mapshaper(input, ops, out) {
  execFileSync("npx", ["mapshaper", "-i", input, ...ops, "-o", join(OUT, out), "format=geojson", "precision=0.0001"], {
    stdio: ["ignore", "inherit", "inherit"],
  });
  console.log(`${out}: ${(statSync(join(OUT, out)).size / 1e6).toFixed(1)} MB`);
}

// each layer: [source, mapshaper operations, output]
const layers = [
  ["ne_10m_land", ["-simplify", "8%", "keep-shapes", "-filter-fields", ""], "land.geojson"],
  ["ne_10m_lakes", ["-filter", "scalerank <= 8", "-simplify", "15%", "keep-shapes", "-filter-fields", "name,scalerank,min_zoom"], "lakes.geojson"],
  ["ne_10m_urban_areas", ["-simplify", "6%", "keep-shapes", "-filter-fields", ""], "urban.geojson"],
  ["ne_10m_rivers_lake_centerlines", ["-filter", "scalerank <= 9", "-simplify", "15%", "-filter-fields", "name,scalerank,min_zoom"], "rivers.geojson"],
  ["ne_10m_admin_0_boundary_lines_land", ["-simplify", "20%", "-filter-fields", ""], "countries-lines.geojson"],
  ["ne_10m_admin_1_states_provinces_lines", ["-simplify", "12%", "-filter-fields", "ADM0_A3"], "states-lines.geojson"],
  [
    "ne_10m_roads",
    ["-filter", "['Major Highway','Secondary Highway','Beltway'].indexOf(type) > -1 && scalerank <= 8", "-simplify", "10%", "-filter-fields", "type,scalerank,min_zoom"],
    "roads.geojson",
  ],
  [
    "ne_10m_populated_places_simple",
    ["-each", "name = nameascii || name, rank = scalerank, cap = adm0cap", "-filter-fields", "name,rank,cap,pop_max,min_zoom"],
    "places.geojson",
  ],
  [
    "ne_50m_admin_0_countries",
    ["-each", "name = NAME_EN || NAME, rank = LABELRANK, min_zoom = MIN_ZOOM", "-points", "inner", "-filter-fields", "name,rank,min_zoom"],
    "countries-labels.geojson",
  ],
  [
    "ne_10m_geography_marine_polys",
    ["-filter", "scalerank <= 3 && featurecla !== 'bay'", "-each", "name = name_en || name", "-points", "inner", "-filter-fields", "name,scalerank,featurecla"],
    "seas-labels.geojson",
  ],
];

for (const [src, ops, out] of layers) mapshaper(await ne(src), ops, out);

for (const font of FONTS)
  for (const range of RANGES) {
    const dir = join(OUT, "fonts", font);
    mkdirSync(dir, { recursive: true });
    await fetchTo(`${GLYPHS}/${encodeURIComponent(font)}/${range}.pbf`, join(dir, `${range}.pbf`));
  }

writeFileSync(
  join(OUT, "ATTRIBUTION.md"),
  "Natural Earth: public domain, https://www.naturalearthdata.com\n" +
    "Noto Sans glyphs: SIL Open Font License 1.1, via https://github.com/protomaps/basemaps-assets\n",
);
console.log("done");
