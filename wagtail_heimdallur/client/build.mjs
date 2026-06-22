import esbuild from "esbuild";

// Wagtail exposes React and Draft.js as `window.React` / `window.DraftJS`.
// Alias the bare imports to those globals so the editor plugin shares the exact
// React and Draft.js instances Draftail itself uses (a second copy would break
// hooks and entity interop) and the bundle stays tiny.
const globals = {
  react: "window.React",
  "draft-js": "window.DraftJS"
};

const wagtailGlobalsPlugin = {
  name: "wagtail-globals",
  setup(build) {
    const filter = /^(react|draft-js)$/;
    build.onResolve({ filter }, (args) => ({
      path: args.path,
      namespace: "wagtail-global"
    }));
    build.onLoad({ filter: /.*/, namespace: "wagtail-global" }, (args) => ({
      contents: `module.exports = ${globals[args.path]};`,
      loader: "js"
    }));
  }
};

await esbuild.build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  format: "iife",
  globalName: "WagtailHeimdallur",
  jsx: "transform",
  jsxFactory: "React.createElement",
  jsxFragment: "React.Fragment",
  minify: true,
  sourcemap: false,
  outfile: "../static/wagtail_heimdallur/js/heimdallur.js",
  plugins: [wagtailGlobalsPlugin],
  logLevel: "info"
});
