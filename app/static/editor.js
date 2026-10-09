document.addEventListener('htmx:responseError', (event) => {
  const error = document.getElementById('error');
  let message = 'Could not save your change. Please try again.';
  try {
    const detail = JSON.parse(event.detail.xhr.responseText).detail;
    if (typeof detail === 'string') message = detail;
  } catch (_) {}
  error.textContent = message;
  error.hidden = false;
});
document.addEventListener('htmx:sendError', () => {
  const error = document.getElementById('error');
  error.textContent = 'Unable to reach the server. Please try again.';
  error.hidden = false;
});
document.addEventListener('htmx:afterSwap', () => {
  document.getElementById('error').hidden = true;
});

// Keep saves local: replacing the editor would discard the next field's focus.
const editStates = new WeakMap();
let pendingSaves = 0;
function editState(element) {
  if (!editStates.has(element)) {
    editStates.set(element, { saved: element.innerText.trim(), queue: Promise.resolve() });
  }
  return editStates.get(element);
}
document.addEventListener('focusin', (event) => {
  if (event.target.matches('.inline-edit')) editState(event.target);
});
document.addEventListener('keydown', (event) => {
  const element = event.target;
  if (!element.matches('.inline-edit') || event.isComposing) return;
  if (event.key === 'Escape') {
    if (element.dataset.newItem || element.dataset.newSection) {
      element.closest(element.dataset.newSection ? 'section' : 'li').remove();
      return;
    }
    element.textContent = editState(element).saved;
    element.blur();
  } else if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    element.blur();
  }
});
document.addEventListener('focusout', (event) => {
  const element = event.target;
  if (!element.matches('.inline-edit')) return;
  const state = editState(element);
  const value = element.innerText.trim();
  const error = document.getElementById('error');
  const status = document.getElementById('save-status');
  if ((element.dataset.newItem || element.dataset.newSection) && !value) {
    element.closest(element.dataset.newSection ? 'section' : 'li').remove();
    return;
  }
  if (!value || value.length > Number(element.dataset.limit)) {
    element.setAttribute('aria-invalid', 'true');
    error.textContent = `${element.getAttribute('aria-label')} must contain 1–${element.dataset.limit} characters. Click the text to correct it.`;
    error.hidden = false;
    status.textContent = 'Changes need attention';
    return;
  }
  element.removeAttribute('aria-invalid');
  pendingSaves += 1;
  status.textContent = 'Saving…';
  state.queue = state.queue.then(async () => {
    if (value === state.saved) return;
    try {
      const response = await fetch(element.dataset.url, {
        method: 'POST',
        headers: { 'HX-Request': 'true', 'X-Inline-Create': element.dataset.newItem || element.dataset.newSection ? 'true' : 'false' },
        body: new URLSearchParams({ [element.dataset.field]: value,
          ...(element.dataset.newItem && element.dataset.parentId ? { parent_id: element.dataset.parentId } : {}) }),
      });
      if (!response.ok) {
        let message = 'Could not save your change.';
        try {
          const body = await response.json();
          if (typeof body.detail === 'string') message = body.detail;
        } catch (_) {}
        throw new Error(message);
      }
      if (element.dataset.newSection) {
        const fragment = new DOMParser().parseFromString(await response.text(), 'text/html');
        const savedSection = fragment.querySelector('section');
        const section = element.closest('section');
        section.dataset.sectionId = savedSection.dataset.sectionId;
        element.dataset.url = savedSection.querySelector('.inline-edit').dataset.url;
        section.querySelector('.section-row').append(savedSection.querySelector('.item-actions'));
        section.append(savedSection.querySelector('ul'));
        delete element.dataset.newSection;
        element.removeAttribute('data-placeholder');
        document.querySelector('.empty-resume')?.remove();
      } else if (element.dataset.newItem) {
        const fragment = new DOMParser().parseFromString(await response.text(), 'text/html');
        const savedItem = fragment.querySelector('li');
        const row = element.closest('li');
        row.dataset.itemId = savedItem.dataset.itemId;
        element.dataset.url = savedItem.querySelector('.inline-edit').dataset.url;
        row.querySelector('.item-row').append(savedItem.querySelector('.item-actions'));
        delete element.dataset.newItem;
        delete element.dataset.parentId;
        element.removeAttribute('data-placeholder');
        element.setAttribute('aria-label', 'Bullet text');
      }
      state.saved = value;
      element.removeAttribute('data-save-failed');
      // Do not overwrite text entered while the request was in flight.
      if (document.activeElement !== element && element.innerText.trim() === value) element.textContent = value;
      if (!document.querySelector('[data-save-failed], [aria-invalid="true"]')) error.hidden = true;
    } catch (failure) {
      element.dataset.saveFailed = 'true';
      error.textContent = `${failure.message} Your text is still here; click it and leave again to retry.`;
      error.hidden = false;
    }
  }).finally(() => {
    pendingSaves -= 1;
    status.textContent = pendingSaves ? 'Saving…' :
      document.querySelector('[data-save-failed], [aria-invalid="true"]') ? 'Changes need attention' : 'Saved';
  });
});

document.addEventListener('click', async (event) => {
  const addSection = event.target.closest('.add-section');
  if (addSection) {
    const editor = addSection.closest('#editor');
    const existing = editor.querySelector('[data-new-section]');
    if (existing) { existing.focus(); return; }
    const section = document.createElement('section');
    section.innerHTML = '<div class="section-row"><h2><span class="inline-edit" contenteditable="plaintext-only" role="textbox" aria-label="Section title" tabindex="0" data-url="/sections" data-field="title" data-limit="200" data-new-section="true" data-placeholder="Section title…"></span></h2></div>';
    editor.insertBefore(section, addSection.closest('.add-section-area'));
    section.querySelector('.inline-edit').focus();
    return;
  }
  const add = event.target.closest('.add-subitem, .add-bullet');
  if (add) {
    const isSubitem = add.matches('.add-subitem');
    const parent = add.closest(isSubitem ? 'li' : 'section');
    let list = parent.querySelector(':scope > ul');
    if (!list) {
      list = document.createElement('ul');
      parent.append(list);
    }
    const existing = list.querySelector(':scope > li > .item-row > [data-new-item]');
    if (existing) { existing.focus(); return; }
    const row = document.createElement('li');
    row.innerHTML = '<div class="item-row"><p class="content inline-edit" contenteditable="plaintext-only" role="textbox" aria-label="New subitem" aria-multiline="true" tabindex="0" data-field="content" data-limit="5000" data-new-item="true" data-placeholder="Write a subitem…"></p></div>';
    const field = row.querySelector('.inline-edit');
    field.dataset.url = `/sections/${add.dataset.sectionId}/items`;
    if (isSubitem) field.dataset.parentId = add.dataset.parentId;
    else {
      field.setAttribute('aria-label', 'New bullet');
      field.dataset.placeholder = 'Write a bullet…';
    }
    list.append(row);
    field.focus();
  }
  const remove = event.target.closest('.delete-item, .delete-section');
  if (remove) {
    const isSection = remove.matches('.delete-section');
    const row = remove.closest(isSection ? 'section' : 'li');
    const message = isSection ? 'Delete this section and all its items?' : 'Delete this item and all its subitems?';
    if (!window.confirm(message)) return;
    remove.disabled = true;
    try {
      const response = await fetch(remove.dataset.url, { method: 'POST', headers: { 'HX-Request': 'true' } });
      if (!response.ok) throw new Error(`Could not delete this ${isSection ? 'section' : 'item'}. Please try again.`);
      row.remove();
    } catch (failure) {
      const error = document.getElementById('error');
      error.textContent = failure.message;
      error.hidden = false;
      remove.disabled = false;
    }
  }
});

let draggedItem = null;
let draggedSection = null;
let movePending = false;
function clearDropHints() {
  document.querySelectorAll('.drop-before, .drop-after, .drop-inside').forEach(node =>
    node.classList.remove('drop-before', 'drop-after', 'drop-inside'));
}
function dropDestination(event) {
  const itemRow = event.target.closest('.item-row');
  if (itemRow) {
    const item = itemRow.closest('li');
    if (!item.dataset.itemId || item === draggedItem || draggedItem.contains(item)) return null;
    const rect = itemRow.getBoundingClientRect();
    const fraction = (event.clientY - rect.top) / rect.height;
    if (fraction < .25) return { parent: item.parentElement.parentElement, before: item, hint: itemRow, style: 'drop-before' };
    if (fraction > .75) return { parent: item.parentElement.parentElement, before: item.nextElementSibling, hint: itemRow, style: 'drop-after' };
    return { parent: item, before: null, hint: itemRow, style: 'drop-inside' };
  }
  const section = event.target.closest('section[data-section-id]');
  if (section && !event.target.closest('li')) return { parent: section, before: null, hint: section.querySelector('.section-row'), style: 'drop-inside' };
  return null;
}
async function saveMove(item, parent, before) {
  if (movePending || pendingSaves || item === parent || item.contains(parent)) return;
  if (document.querySelector('[data-new-item]')) {
    const error = document.getElementById('error');
    error.textContent = 'Finish or cancel the new bullet before moving items.';
    error.hidden = false;
    return;
  }
  let list = parent.querySelector(':scope > ul');
  const siblings = list ? [...list.children].filter(node => node !== item) : [];
  const position = before ? siblings.indexOf(before) : siblings.length;
  if (position < 0) return;
  const section = parent.closest('section[data-section-id]');
  const body = new URLSearchParams({ section_id: section.dataset.sectionId, position });
  if (parent.matches('li')) body.set('parent_id', parent.dataset.itemId);
  movePending = true;
  const status = document.getElementById('save-status');
  status.textContent = 'Saving order…';
  try {
    const response = await fetch(`/items/${item.dataset.itemId}/move`, { method: 'POST', body });
    if (!response.ok) {
      let message = 'Could not move this bullet. Please try again.';
      try { const data = await response.json(); if (typeof data.detail === 'string') message = data.detail; } catch (_) {}
      throw new Error(message);
    }
    if (!list) { list = document.createElement('ul'); parent.append(list); }
    list.insertBefore(item, before);
    item.querySelectorAll('.add-subitem').forEach(button => button.dataset.sectionId = section.dataset.sectionId);
    status.textContent = 'Saved';
    item.querySelector('.drag-handle').focus();
  } catch (failure) {
    const error = document.getElementById('error');
    error.textContent = failure.message;
    error.hidden = false;
    status.textContent = 'Move was not saved';
  } finally { movePending = false; }
}
document.addEventListener('dragstart', event => {
  const sectionHandle = event.target.closest('.section-drag-handle');
  if (sectionHandle) {
    if (movePending || pendingSaves) { event.preventDefault(); return; }
    draggedSection = sectionHandle.closest('section');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', draggedSection.dataset.sectionId);
    draggedSection.classList.add('dragging');
    return;
  }
  const handle = event.target.closest('.drag-handle');
  if (!handle) return;
  if (movePending || pendingSaves) { event.preventDefault(); return; }
  draggedItem = handle.closest('li');
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', draggedItem.dataset.itemId);
  draggedItem.classList.add('dragging');
});
document.addEventListener('dragover', event => {
  if (draggedSection) {
    clearDropHints();
    const destination = sectionDropDestination(event);
    if (destination) {
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      destination.hint.classList.add(destination.style);
    }
    return;
  }
  if (!draggedItem) return;
  clearDropHints();
  const destination = dropDestination(event);
  if (!destination) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = 'move';
  destination.hint.classList.add(destination.style);
});
document.addEventListener('drop', event => {
  if (draggedSection) {
    event.preventDefault();
    const destination = sectionDropDestination(event);
    clearDropHints();
    if (destination) saveSectionMove(draggedSection, destination.before);
    return;
  }
  if (!draggedItem) return;
  event.preventDefault();
  const destination = dropDestination(event);
  clearDropHints();
  if (destination) saveMove(draggedItem, destination.parent, destination.before);
});
document.addEventListener('dragend', () => {
  if (draggedSection) draggedSection.classList.remove('dragging');
  draggedSection = null;
  if (draggedItem) draggedItem.classList.remove('dragging');
  draggedItem = null;
  clearDropHints();
});
document.addEventListener('keydown', event => {
  const handle = event.target.closest('.drag-handle');
  if (!handle || !['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) return;
  event.preventDefault();
  const item = handle.closest('li');
  const parent = item.parentElement.parentElement;
  if (event.key === 'ArrowUp' && item.previousElementSibling) saveMove(item, parent, item.previousElementSibling);
  if (event.key === 'ArrowDown' && item.nextElementSibling) saveMove(item, parent, item.nextElementSibling.nextElementSibling);
  if (event.key === 'ArrowRight' && item.previousElementSibling) saveMove(item, item.previousElementSibling, null);
  if (event.key === 'ArrowLeft' && parent.matches('li')) saveMove(item, parent.parentElement.parentElement, parent.nextElementSibling);
});

function sectionDropDestination(event) {
  const target = event.target.closest('section[data-section-id]');
  if (target && target !== draggedSection) {
    const rect = target.getBoundingClientRect();
    const before = event.clientY < rect.top + rect.height / 2;
    return { before: before ? target : target.nextElementSibling, hint: target, style: before ? 'drop-before' : 'drop-after' };
  }
  const area = event.target.closest('.add-section-area');
  return area ? { before: area, hint: area, style: 'drop-before' } : null;
}
async function saveSectionMove(section, before) {
  if (movePending || pendingSaves || before === section) return;
  if (document.querySelector('[data-new-section]')) {
    const error = document.getElementById('error');
    error.textContent = 'Finish or cancel the new section before reordering sections.';
    error.hidden = false;
    return;
  }
  const editor = section.parentElement;
  const siblings = [...editor.querySelectorAll(':scope > section[data-section-id]')].filter(node => node !== section);
  const position = before?.matches('section[data-section-id]') ? siblings.indexOf(before) : siblings.length;
  if (position < 0) return;
  movePending = true;
  const status = document.getElementById('save-status');
  status.textContent = 'Saving section order…';
  try {
    const response = await fetch(`/sections/${section.dataset.sectionId}/move`, {
      method: 'POST', body: new URLSearchParams({ position }),
    });
    if (!response.ok) throw new Error('Could not reorder this section. Please try again.');
    editor.insertBefore(section, before || editor.querySelector('.add-section-area'));
    status.textContent = 'Saved';
    section.querySelector('.section-drag-handle').focus();
  } catch (failure) {
    const error = document.getElementById('error');
    error.textContent = failure.message;
    error.hidden = false;
    status.textContent = 'Section order was not saved';
  } finally { movePending = false; }
}
document.addEventListener('keydown', event => {
  const handle = event.target.closest('.section-drag-handle');
  if (!handle || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
  event.preventDefault();
  const section = handle.closest('section');
  if (event.key === 'ArrowUp' && section.previousElementSibling?.matches('section[data-section-id]')) {
    saveSectionMove(section, section.previousElementSibling);
  }
  if (event.key === 'ArrowDown' && section.nextElementSibling?.matches('section[data-section-id]')) {
    saveSectionMove(section, section.nextElementSibling.nextElementSibling);
  }
});
