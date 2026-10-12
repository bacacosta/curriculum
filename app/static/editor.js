const pendingMutations = new Set();
function mutationRequest(...args) {
  const request = fetch(...args);
  pendingMutations.add(request);
  request.then(() => pendingMutations.delete(request), () => pendingMutations.delete(request));
  return request;
}

document.addEventListener('click', async (event) => {
  const button = event.target.closest('.export-pdf');
  if (!button || button.disabled) return;
  button.disabled = true;
  const editor = document.getElementById('editor');
  editor.inert = true;
  const error = document.getElementById('error');
  try {
    await Promise.all([...document.querySelectorAll('.inline-edit')].map(element => editStates.get(element)?.queue));
    await Promise.all([...pendingMutations]);
    if (document.querySelector('[data-save-failed], [aria-invalid="true"]')) throw new Error('Please fix unsaved changes before exporting.');
    const response = await fetch('/export.pdf');
    if (!response.ok) throw new Error('Could not export the PDF. Please try again.');
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = 'resume.pdf';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  } finally { editor.inert = false; button.disabled = false; }
});

// Keep saves local: replacing the editor would discard the next field's focus.
const editStates = new WeakMap();
let pendingSaves = 0;
let savedStatusTimer;
let savingStatusTimer;
let savingStartedAt = null;
function setSaveStatus(message) {
  clearTimeout(savedStatusTimer);
  clearTimeout(savingStatusTimer);
  const status = document.getElementById('save-status');
  if (message.startsWith('Saving')) {
    if (savingStartedAt === null) savingStartedAt = performance.now();
  } else if (message === 'Saved' && savingStartedAt !== null) {
    const remaining = 2000 - (performance.now() - savingStartedAt);
    if (remaining > 0) {
      savingStatusTimer = setTimeout(() => setSaveStatus('Saved'), remaining);
      return;
    }
    savingStartedAt = null;
  } else {
    savingStartedAt = null;
  }
  status.textContent = message;
  status.classList.toggle('has-save-icon', message === 'Saved' || message.startsWith('Saving'));
  if (message === 'Saved') {
    savedStatusTimer = setTimeout(() => {
      if (status.textContent === 'Saved') {
        status.textContent = '';
        status.classList.remove('has-save-icon');
      }
    }, 5000);
  }
}

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
    if (element.dataset.newBullet || element.dataset.newSection) {
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
  if ((element.dataset.newBullet || element.dataset.newSection) && !value) {
    element.closest(element.dataset.newSection ? 'section' : 'li').remove();
    return;
  }
  if ((!value && !element.dataset.allowEmpty) || value.length > Number(element.dataset.limit)) {
    element.setAttribute('aria-invalid', 'true');
    error.textContent = `${element.getAttribute('aria-label')} must contain ${element.dataset.allowEmpty ? '0' : '1'}–${element.dataset.limit} characters. Click the text to correct it.`;
    error.hidden = false;
    setSaveStatus('Changes need attention');
    return;
  }
  element.removeAttribute('aria-invalid');
  pendingSaves += 1;
  setSaveStatus('Saving…');
  state.queue = state.queue.then(async () => {
    if (value === state.saved) return;
    try {
      const response = await mutationRequest(element.dataset.url, {
        method: 'POST',
        headers: { 'X-Editor-Request': 'true', 'X-Inline-Create': element.dataset.newBullet || element.dataset.newSection ? 'true' : 'false' },
        body: new URLSearchParams({ [element.dataset.field]: value,
          ...(element.dataset.newBullet && element.dataset.parentId ? { parent_id: element.dataset.parentId } : {}) }),
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
        section.querySelector('.section-row').append(savedSection.querySelector('.bullet-actions'));
        section.append(savedSection.querySelector('ul'));
        delete element.dataset.newSection;
        element.removeAttribute('data-placeholder');
        document.querySelector('.empty-resume')?.remove();
      } else if (element.dataset.newBullet) {
        const fragment = new DOMParser().parseFromString(await response.text(), 'text/html');
        const savedBullet = fragment.querySelector('li');
        const row = element.closest('li');
        row.dataset.bulletId = savedBullet.dataset.bulletId;
        element.dataset.url = savedBullet.querySelector('.inline-edit').dataset.url;
        row.querySelector('.bullet-row').append(savedBullet.querySelector('.bullet-actions'));
        delete element.dataset.newBullet;
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
    setSaveStatus(pendingSaves ? 'Saving…' :
      document.querySelector('[data-save-failed], [aria-invalid="true"]') ? 'Changes need attention' : 'Saved');
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
  const add = event.target.closest('.add-subbullet, .add-bullet');
  if (add) {
    const isSubbullet = add.matches('.add-subbullet');
    const parent = add.closest(isSubbullet ? 'li' : 'section');
    let list = parent.querySelector(':scope > ul');
    if (!list) {
      list = document.createElement('ul');
      parent.append(list);
    }
    const existing = list.querySelector(':scope > li > .bullet-row > [data-new-bullet]');
    if (existing) { existing.focus(); return; }
    const row = document.createElement('li');
    row.innerHTML = '<div class="bullet-row"><p class="content inline-edit" contenteditable="plaintext-only" role="textbox" aria-label="New subbullet" aria-multiline="true" tabindex="0" data-field="content" data-limit="5000" data-new-bullet="true" data-placeholder="Write a subbullet…"></p></div>';
    const field = row.querySelector('.inline-edit');
    field.dataset.url = `/sections/${add.dataset.sectionId}/bullets`;
    if (isSubbullet) field.dataset.parentId = add.dataset.parentId;
    else {
      field.setAttribute('aria-label', 'New bullet');
      field.dataset.placeholder = 'Write a bullet…';
    }
    list.append(row);
    field.focus();
  }
  const remove = event.target.closest('.delete-bullet, .delete-section');
  if (remove) {
    const isSection = remove.matches('.delete-section');
    const row = remove.closest(isSection ? 'section' : 'li');
    const message = isSection ? 'Delete this section and all its bullets?' : 'Delete this bullet and all its subbullets?';
    if (!window.confirm(message)) return;
    remove.disabled = true;
    try {
      const response = await mutationRequest(remove.dataset.url, { method: 'POST', headers: { 'X-Editor-Request': 'true' } });
      if (!response.ok) throw new Error(`Could not delete this ${isSection ? 'section' : 'bullet'}. Please try again.`);
      row.remove();
    } catch (failure) {
      const error = document.getElementById('error');
      error.textContent = failure.message;
      error.hidden = false;
      remove.disabled = false;
    }
  }
});

let draggedBullet = null;
let draggedSection = null;
let movePending = false;
function clearDropHints() {
  document.querySelectorAll('.drop-before, .drop-after, .drop-inside').forEach(node =>
    node.classList.remove('drop-before', 'drop-after', 'drop-inside'));
}
function dropDestination(event) {
  const bulletRow = event.target.closest('.bullet-row');
  if (bulletRow) {
    const bullet = bulletRow.closest('li');
    if (!bullet.dataset.bulletId || bullet === draggedBullet || draggedBullet.contains(bullet)) return null;
    const rect = bulletRow.getBoundingClientRect();
    const fraction = (event.clientY - rect.top) / rect.height;
    if (fraction < .25) return { parent: bullet.parentElement.parentElement, before: bullet, hint: bulletRow, style: 'drop-before' };
    if (fraction > .75) return { parent: bullet.parentElement.parentElement, before: bullet.nextElementSibling, hint: bulletRow, style: 'drop-after' };
    return { parent: bullet, before: null, hint: bulletRow, style: 'drop-inside' };
  }
  const section = event.target.closest('section[data-section-id]');
  if (section && !event.target.closest('li')) return { parent: section, before: null, hint: section.querySelector('.section-row'), style: 'drop-inside' };
  return null;
}
async function saveMove(bullet, parent, before) {
  if (movePending || pendingSaves || bullet === parent || bullet.contains(parent)) return;
  if (document.querySelector('[data-new-bullet]')) {
    const error = document.getElementById('error');
    error.textContent = 'Finish or cancel the new bullet before moving bullets.';
    error.hidden = false;
    return;
  }
  let list = parent.querySelector(':scope > ul');
  const siblings = list ? [...list.children].filter(node => node !== bullet) : [];
  const position = before ? siblings.indexOf(before) : siblings.length;
  if (position < 0) return;
  const section = parent.closest('section[data-section-id]');
  const body = new URLSearchParams({ section_id: section.dataset.sectionId, position });
  if (parent.matches('li')) body.set('parent_id', parent.dataset.bulletId);
  movePending = true;
  setSaveStatus('Saving bullet order…');
  try {
    const response = await mutationRequest(`/bullets/${bullet.dataset.bulletId}/move`, { method: 'POST', body });
    if (!response.ok) {
      let message = 'Could not move this bullet. Please try again.';
      try { const data = await response.json(); if (typeof data.detail === 'string') message = data.detail; } catch (_) {}
      throw new Error(message);
    }
    if (!list) { list = document.createElement('ul'); parent.append(list); }
    list.insertBefore(bullet, before);
    bullet.querySelectorAll('.add-subbullet').forEach(button => button.dataset.sectionId = section.dataset.sectionId);
    setSaveStatus('Saved');
    bullet.querySelector('.drag-handle').focus();
  } catch (failure) {
    const error = document.getElementById('error');
    error.textContent = failure.message;
    error.hidden = false;
    setSaveStatus('Move was not saved');
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
  draggedBullet = handle.closest('li');
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', draggedBullet.dataset.bulletId);
  draggedBullet.classList.add('dragging');
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
  if (!draggedBullet) return;
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
  if (!draggedBullet) return;
  event.preventDefault();
  const destination = dropDestination(event);
  clearDropHints();
  if (destination) saveMove(draggedBullet, destination.parent, destination.before);
});
document.addEventListener('dragend', () => {
  if (draggedSection) draggedSection.classList.remove('dragging');
  draggedSection = null;
  if (draggedBullet) draggedBullet.classList.remove('dragging');
  draggedBullet = null;
  clearDropHints();
});
document.addEventListener('keydown', event => {
  const handle = event.target.closest('.drag-handle');
  if (!handle || !['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) return;
  event.preventDefault();
  const bullet = handle.closest('li');
  const parent = bullet.parentElement.parentElement;
  if (event.key === 'ArrowUp' && bullet.previousElementSibling) saveMove(bullet, parent, bullet.previousElementSibling);
  if (event.key === 'ArrowDown' && bullet.nextElementSibling) saveMove(bullet, parent, bullet.nextElementSibling.nextElementSibling);
  if (event.key === 'ArrowRight' && bullet.previousElementSibling) saveMove(bullet, bullet.previousElementSibling, null);
  if (event.key === 'ArrowLeft' && parent.matches('li')) saveMove(bullet, parent.parentElement.parentElement, parent.nextElementSibling);
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
  setSaveStatus('Saving section order…');
  try {
    const response = await mutationRequest(`/sections/${section.dataset.sectionId}/move`, {
      method: 'POST', body: new URLSearchParams({ position }),
    });
    if (!response.ok) throw new Error('Could not reorder this section. Please try again.');
    editor.insertBefore(section, before || editor.querySelector('.add-section-area'));
    setSaveStatus('Saved');
    section.querySelector('.section-drag-handle').focus();
  } catch (failure) {
    const error = document.getElementById('error');
    error.textContent = failure.message;
    error.hidden = false;
    setSaveStatus('Section order was not saved');
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
