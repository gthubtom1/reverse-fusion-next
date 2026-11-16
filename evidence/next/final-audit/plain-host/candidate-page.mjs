import {restore, change, view} from './core.mjs';

const controls = Object.fromEntries(
  ['add', 'name', 'tag', 'quantity', 'query', 'order', 'rows', 'empty', 'summary', 'error', 'clear']
    .map(id => [id, document.getElementById(id)])
);
const storageKey = 'rf-owned-desk-v1';
let current = restore(localStorage.getItem(storageKey));

function refresh() {
  const visible = view(current, controls.query.value, controls.order.value);
  const fragment = document.createDocumentFragment();
  for (const record of visible.entries) {
    const row = document.createElement('tr');
    for (const field of ['name', 'tag', 'quantity']) {
      const td = document.createElement('td');
      td.textContent = record[field];
      row.appendChild(td);
    }
    const td = document.createElement('td');
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'remove';
    remove.textContent = '删除';
    remove.addEventListener('click', () => commit({type: 'remove', id: record.id}));
    td.appendChild(remove);
    row.appendChild(td);
    fragment.appendChild(row);
  }
  controls.rows.replaceChildren(fragment);
  controls.empty.hidden = visible.items !== 0;
  controls.empty.textContent = current.entries.length > 0 ? '没有匹配的条目。' : '还没有条目，先添加一个吧。';
  controls.summary.textContent = `${visible.items} 项 · 共 ${visible.quantity} 件`;
}

function commit(action) {
  try {
    const proposed = change(current, action);
    localStorage.setItem(storageKey, JSON.stringify(proposed));
    current = proposed;
    controls.error.textContent = '';
    refresh();
    return true;
  } catch (failure) {
    controls.error.textContent = failure.message;
    return false;
  }
}

controls.add.addEventListener('submit', event => {
  event.preventDefault();
  if (commit({type: 'add', name: controls.name.value, tag: controls.tag.value, quantity: controls.quantity.value})) {
    controls.name.value = '';
    controls.name.focus();
  }
});
controls.query.addEventListener('input', refresh);
controls.order.addEventListener('change', refresh);
controls.clear.addEventListener('click', () => {
  if (window.confirm('确定清空全部条目吗？')) commit({type: 'clear'});
});
refresh();
