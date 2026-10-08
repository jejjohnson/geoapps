/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_BASEMAP_STYLE?: string;
  readonly VITE_IMAGERY_TILES?: string;
}

declare module "world-atlas/countries-50m.json" {
  const topology: import("topojson-specification").Topology;
  export default topology;
}
