// trader viewer:唯一的交互——思考流折叠控制
function foldAll(collapse) {
  document.querySelectorAll('details.step').forEach(d => d.open = !collapse);
}

function compareSelected(onlyCheck) {
  const ids = [...document.querySelectorAll('.run-cb:checked')].map(c => c.value);
  if (onlyCheck) return;
  if (ids.length !== 2) { alert('请恰好勾选两场'); return; }
  location.href = '/compare?runs=' + ids.join(',');
}
