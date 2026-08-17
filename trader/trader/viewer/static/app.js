// trader viewer:唯一的交互——思考流折叠控制
function foldAll(collapse) {
  document.querySelectorAll('details.step').forEach(d => d.open = !collapse);
}
