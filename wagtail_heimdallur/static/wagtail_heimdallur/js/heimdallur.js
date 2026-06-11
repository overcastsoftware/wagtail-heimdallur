(function () {
  function applyAnnotationCorrection(text, annotation) {
    return [
      text.slice(0, annotation.orig_start_idx),
      annotation.changed_string,
      text.slice(annotation.orig_end_idx)
    ].join("");
  }

  window.WagtailHeimdallur = Object.assign({}, window.WagtailHeimdallur || {}, {
    applyAnnotationCorrection: applyAnnotationCorrection
  });
})();
