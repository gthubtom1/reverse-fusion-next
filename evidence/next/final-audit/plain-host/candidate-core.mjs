// Independent implementation of the observed v1 storage and behavior contract.
const fold = value => value.toLocaleLowerCase('en-US');
export const initial = () => ({version: 1, next: 1, entries: []});

export function restore(serialized) {
  try {
    const saved = JSON.parse(serialized);
    if (saved.version !== 1 || !Number.isSafeInteger(saved.next) || saved.next < 1 ||
        !Array.isArray(saved.entries)) return initial();
    const seen = new Set();
    for (const record of saved.entries) {
      if (!Number.isSafeInteger(record.id) || record.id < 1 || record.id >= saved.next ||
          seen.has(record.id) || typeof record.name !== 'string' || typeof record.tag !== 'string' ||
          !Number.isInteger(record.quantity) || record.quantity < 1 || record.quantity > 99) return initial();
      seen.add(record.id);
    }
    return saved;
  } catch {
    return initial();
  }
}

export function change(state, action) {
  const draft = structuredClone(state);
  switch (action.type) {
    case 'clear': return initial();
    case 'remove': {
      const position = draft.entries.findIndex(record => record.id === action.id);
      if (position < 0) throw new Error('条目不存在');
      draft.entries.splice(position, 1);
      return draft;
    }
    case 'add': {
      const name = String(action.name ?? '').trim();
      const tag = String(action.tag ?? '').trim() || '未分类';
      const quantity = Number(action.quantity);
      if (name.length === 0) throw new Error('请填写名称');
      if (name.length > 32) throw new Error('名称最多32个字符');
      if (!Number.isInteger(quantity) || quantity < 1 || quantity > 99) throw new Error('数量须为1至99的整数');
      for (const record of draft.entries) {
        if (record.tag === tag && fold(record.name) === fold(name)) throw new Error('该分类中已有同名条目');
      }
      const id = draft.next;
      draft.next += 1;
      draft.entries.push({id, name, tag, quantity});
      return draft;
    }
    default: throw new Error('未知操作');
  }
}

export function view(state, query = '', order = 'newest') {
  const needle = fold(String(query).trim());
  const entries = [];
  for (const record of state.entries) {
    if (fold(record.name + '\n' + record.tag).includes(needle)) entries.push(record);
  }
  entries.sort(order === 'name'
    ? (left, right) => left.name.localeCompare(right.name, 'zh-CN') || left.id - right.id
    : (left, right) => right.id - left.id);
  let quantity = 0;
  for (const record of entries) quantity += record.quantity;
  return {entries, items: entries.length, quantity};
}
