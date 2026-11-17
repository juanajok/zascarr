/* #1058: atajo de búsqueda, solo en Biblioteca. */
(() => {
  const buscador = document.querySelector('#f-q, input[name="q"]');
  if (!buscador) return;
  document.addEventListener("keydown", (evento) => {
    const activo = document.activeElement;
    const editable = activo && (activo.matches("input, textarea, select") || activo.isContentEditable);
    if (editable) return;
    const barra = evento.key === "/" || (evento.ctrlKey && evento.key.toLowerCase() === "k");
    if (!barra) return;
    evento.preventDefault();
    buscador.focus();
    buscador.select?.();
  });
})();
