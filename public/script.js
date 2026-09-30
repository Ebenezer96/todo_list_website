/* To Do app. Sections: 1 State, 2 Storage, 3 Actions, 4 Rendering, 5 Events. */
(function () {
  'use strict';

  /* ---------- 1. State ---------- */
  var STORAGE_KEY = 'todo-app.tasks.v1';
  var BACKUP_KEY = STORAGE_KEY + '.unreadable-backup';
  var MAX_LENGTH = 200;

  var tasks = [];            // [{ id, title, completed, createdAt }]
  var filter = 'all';        // 'all' | 'active' | 'completed'
  var editingId = null;      // id of the task being edited
  var editDraft = '';        // text typed in the edit box (survives re-renders)
  var confirmingId = null;   // id of the task awaiting delete confirmation
  var storage = 'ok';        // 'ok' | 'unavailable' | 'corrupt'
  var rawSaved = null;       // unreadable saved text (corrupt mode only)
  var saveError = false;     // last write attempt failed
  var dirty = false;         // in-memory tasks differ from what is saved

  var $ = function (id) { return document.getElementById(id); };
  var list = $('task-list'), addForm = $('add-form'), newTitle = $('new-title'), addError = $('add-error');

  /* ---------- 2. Storage ---------- */
  function isValidTask(t) {
    return t !== null && typeof t === 'object' &&
      typeof t.id === 'string' && t.id !== '' &&
      typeof t.title === 'string' && validate(t.title.trim()) === '' &&
      typeof t.completed === 'boolean' &&
      typeof t.createdAt === 'string';
  }

  // Returns an array of tasks, or null if the text is not a valid task list.
  function parseTasks(raw) {
    var data, seen = {};
    try { data = JSON.parse(raw); } catch (e) { return null; }
    if (!Array.isArray(data)) return null;
    for (var i = 0; i < data.length; i++) {
      if (!isValidTask(data[i]) || seen[data[i].id]) return null;
      seen[data[i].id] = true;
    }
    return data;
  }

  function load() {
    var raw;
    try { raw = window.localStorage.getItem(STORAGE_KEY); }
    catch (e) { return { status: 'unavailable', tasks: [] }; }
    if (raw === null) return { status: 'ok', tasks: [] };
    var parsed = parseTasks(raw);
    return parsed ? { status: 'ok', tasks: parsed } : { status: 'corrupt', tasks: [], raw: raw };
  }

  // Returns true only if the write really succeeded.
  function save() {
    if (storage !== 'ok') return false;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
      saveError = false;
      return true;
    } catch (e) {
      saveError = true;
      return false;
    }
  }

  // Pick up changes made in other tabs. Skipped when we hold unsaved work.
  function refreshFromStorage() {
    if (storage !== 'ok' || dirty) return;
    var r = load();
    if (r.status === 'ok') tasks = r.tasks;
    else { storage = r.status; rawSaved = r.raw || null; dirty = true; }
    if (editingId && !find(editingId)) editingId = null;
    if (confirmingId && !find(confirmingId)) confirmingId = null;
  }

  /* ---------- 3. Actions ---------- */
  function find(id) { return tasks.filter(function (t) { return t.id === id; })[0]; }
  function isVisible(t) { return filter === 'all' || (filter === 'active') === !t.completed; }
  function visibleTasks() { return tasks.filter(isVisible); }

  function validate(title) {
    var blank = title.replace(/[\s\u200B-\u200D\u2060\uFEFF]/g, '') === '';
    if (blank) return 'Please enter a task title. It cannot be blank.';
    var n = Array.from(title).length;
    if (n > MAX_LENGTH) return 'Task titles can be at most ' + MAX_LENGTH + ' characters. This one has ' + n + '.';
    return '';
  }

  function newId() {
    var id;
    do {
      id = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
        : Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
    } while (find(id));
    return id;
  }

  // Runs every change: refresh, apply, save, render, announce. fn returns false if the task is gone.
  function change(fn, message) {
    refreshFromStorage();
    if (!fn()) {
      render();
      announce('That task no longer exists. It may have been deleted in another tab.');
      return false;
    }
    var saved = save();
    dirty = !saved;
    render();
    announce(saved ? message : message + ' It was not saved. See the warning on the page.');
    return true;
  }

  // Focus a sensible element after a re-render (the old element may be gone).
  function focusAfter(id, index, selector) {
    var vis = visibleTasks(), target;
    if (vis.some(function (t) { return t.id === id; })) target = id;
    else if (vis.length) target = vis[Math.min(index, vis.length - 1)].id;
    var li = target && rowFor(target);
    var el = li && (li.querySelector(selector) || li.querySelector('input[type="checkbox"]'));
    (el || newTitle).focus();
  }

  function rowFor(id) {
    return Array.prototype.filter.call(list.children, function (li) { return li.dataset.id === id; })[0];
  }

  function addTask() {
    var title = newTitle.value.trim(), error = validate(title);
    newTitle.setAttribute('aria-invalid', error ? 'true' : 'false');
    addError.textContent = error;
    if (error) { newTitle.focus(); return; }
    var task = { id: '', title: title, completed: false, createdAt: new Date().toISOString() };
    var hidden = filter === 'completed';
    change(function () { task.id = newId(); tasks.push(task); return true; },
      hidden ? 'Task added. It is active, so it is not shown in the Completed view.' : 'Task added.');
    newTitle.value = '';
    newTitle.focus();
  }

  function setCompleted(id, completed) {
    var index = visibleTasks().map(function (t) { return t.id; }).indexOf(id);
    change(function () {
      var t = find(id);
      if (!t) return false;
      t.completed = completed;
      return true;
    }, completed ? 'Task marked completed.' : 'Task marked active.');
    focusAfter(id, index, 'input[type="checkbox"]');
  }

  function startEdit(id) {
    editingId = id; confirmingId = null; editDraft = find(id).title;
    render();
    var input = rowFor(id).querySelector('input[type="text"]');
    input.focus(); input.select();
  }

  function saveEdit(id) {
    var title = editDraft.trim(), error = validate(title);
    var row = rowFor(id), input = row.querySelector('input[type="text"]');
    input.setAttribute('aria-invalid', error ? 'true' : 'false');
    row.querySelector('.error').textContent = error;
    if (error) { input.focus(); return; }
    var index = visibleTasks().map(function (t) { return t.id; }).indexOf(id);
    editingId = null;
    change(function () {
      var t = find(id);
      if (!t) return false;
      t.title = title;   // id, completed and createdAt are left untouched
      return true;
    }, 'Task updated.');
    focusAfter(id, index, '[data-action="edit"]');
  }

  function cancelEdit(id) {
    editingId = null;
    render();
    announce('Edit cancelled.');
    focusAfter(id, 0, '[data-action="edit"]');
  }

  function askDelete(id) {
    confirmingId = id; editingId = null;
    render();
    rowFor(id).querySelector('[data-action="cancel-delete"]').focus();  // safe default
  }

  function cancelDelete(id) {
    confirmingId = null;
    render();
    announce('Deletion cancelled. The task was kept.');
    focusAfter(id, 0, '[data-action="delete"]');
  }

  function deleteTask(id) {
    var index = visibleTasks().map(function (t) { return t.id; }).indexOf(id);
    confirmingId = null;
    change(function () {
      var i = tasks.map(function (t) { return t.id; }).indexOf(id);
      if (i < 0) return false;
      tasks.splice(i, 1);
      return true;
    }, 'Task deleted.');
    focusAfter(null, index, 'input[type="checkbox"]');
  }

  function downloadRaw() {
    var url = URL.createObjectURL(new Blob([rawSaved || ''], { type: 'text/plain' }));
    var a = document.createElement('a');
    a.href = url; a.download = 'todo-unreadable-data.txt';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function startFresh() {
    if (!window.confirm('Discard the unreadable saved data? A backup copy will be kept in this browser first.')) return;
    try {
      window.localStorage.setItem(BACKUP_KEY, rawSaved || '');   // back up first
      storage = 'ok';
      if (!save()) throw new Error('save failed');
    } catch (e) {
      storage = 'corrupt';
      announce('Nothing was discarded, because a backup copy could not be stored. Download the data first.');
      return;
    }
    rawSaved = null; dirty = false;
    render();
    announce('Unreadable data discarded. Your current list is now saved.');
  }

  /* ---------- 4. Rendering ---------- */
  function announce(message) {
    var live = $('live');
    live.textContent = '';
    setTimeout(function () { live.textContent = message; }, 50);
  }

  function button(text, action, className, label) {
    var b = document.createElement('button');
    b.type = 'button'; b.textContent = text; b.dataset.action = action;
    if (className) b.className = className;
    if (label) b.setAttribute('aria-label', label);
    return b;
  }

  function taskRow(t) {
    var li = document.createElement('li');
    li.className = 'task' + (t.completed ? ' done' : '');
    li.dataset.id = t.id;

    if (editingId === t.id) {
      var form = document.createElement('form');
      form.noValidate = true; form.dataset.id = t.id;
      var input = document.createElement('input');
      input.type = 'text'; input.value = editDraft; input.autocomplete = 'off';
      input.setAttribute('aria-label', 'Edit task title');
      input.setAttribute('aria-describedby', 'edit-error');
      var err = document.createElement('p');
      err.className = 'error'; err.id = 'edit-error'; err.setAttribute('role', 'alert');
      var saveBtn = button('Save', 'save'); saveBtn.type = 'submit';
      form.append(input, saveBtn, button('Cancel', 'cancel-edit'), err);
      li.appendChild(form);
    } else if (confirmingId === t.id) {
      var box = document.createElement('div');
      box.className = 'confirm';
      var q = document.createElement('p');
      q.textContent = 'Delete this task: \u201C' + t.title + '\u201D?';
      box.append(q, button('Yes, delete', 'confirm-delete', 'danger-solid'), button('Cancel', 'cancel-delete'));
      li.appendChild(box);
    } else {
      var main = document.createElement('div');
      main.className = 'task-main';
      var cb = document.createElement('input');
      cb.type = 'checkbox'; cb.checked = t.completed; cb.id = 'cb-' + t.id;
      var label = document.createElement('label');
      label.htmlFor = cb.id; label.textContent = t.title;   // textContent: text is never parsed as HTML
      main.append(cb, label);
      li.appendChild(main);
      if (t.completed) {
        var badge = document.createElement('span');
        badge.className = 'badge'; badge.textContent = 'Completed';
        li.appendChild(badge);
      }
      li.append(button('Edit', 'edit', '', 'Edit task: ' + t.title),
                button('Delete', 'delete', 'danger', 'Delete task: ' + t.title));
    }
    return li;
  }

  function render() {
    var vis = visibleTasks(), done = tasks.filter(function (t) { return t.completed; }).length;
    list.replaceChildren.apply(list, vis.map(taskRow));

    var empty = $('empty');
    empty.hidden = vis.length > 0;
    if (!tasks.length) empty.textContent = 'No tasks yet. Add your first task above.';
    else if (filter === 'active') empty.textContent = 'No active tasks. Everything is completed.';
    else empty.textContent = 'No completed tasks yet.';

    $('count').textContent = tasks.length + (tasks.length === 1 ? ' task: ' : ' tasks: ') +
      (tasks.length - done) + ' active, ' + done + ' completed';
    Array.prototype.forEach.call($('filters').children, function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.filter === filter));
    });
    renderStorageStatus();
  }

  function renderStorageStatus() {
    var msg = '', status = 'All changes are saved in this browser.';
    if (storage === 'unavailable') {
      msg = 'Your browser is blocking storage (private browsing or a setting can cause this). You can keep using the list, but your tasks will be lost when you close or refresh this page.';
      status = 'Not saved: storage is unavailable.';
    } else if (storage === 'corrupt') {
      msg = 'Your saved tasks could not be read, so they were not loaded. Saving is switched off so nothing is overwritten. You can download the unreadable data, or discard it and start fresh.';
      status = 'Not saved: saving is switched off to protect your existing data.';
    } else if (saveError) {
      msg = 'Your latest changes could not be saved (storage may be full or blocked). Your tasks exist only in this open page and will be lost if you close it.';
      status = 'Not saved: the last save failed.';
    }
    // Only touch the text when it changes, so screen readers do not repeat it on every render.
    if ($('storage-message').textContent !== msg) $('storage-message').textContent = msg;
    $('storage-banner').hidden = !msg;
    $('storage-actions').hidden = storage !== 'corrupt';
    $('save-status').textContent = status;
  }

  /* ---------- 5. Events ---------- */
  addForm.addEventListener('submit', function (e) { e.preventDefault(); addTask(); });
  newTitle.addEventListener('input', function () { addError.textContent = ''; newTitle.setAttribute('aria-invalid', 'false'); });

  $('filters').addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    filter = b.dataset.filter; editingId = null; confirmingId = null;
    render();
    announce('Showing ' + filter + ' tasks.');
  });

  list.addEventListener('change', function (e) {
    if (e.target.type === 'checkbox') setCompleted(e.target.closest('li').dataset.id, e.target.checked);
  });

  list.addEventListener('input', function (e) {
    if (e.target.type === 'text') { editDraft = e.target.value; e.target.setAttribute('aria-invalid', 'false'); }
  });

  list.addEventListener('submit', function (e) {
    e.preventDefault();
    saveEdit(e.target.dataset.id);
  });

  list.addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b || !b.dataset.action) return;
    var id = b.closest('li').dataset.id;
    var actions = {
      'edit': startEdit, 'cancel-edit': cancelEdit,
      'delete': askDelete, 'cancel-delete': cancelDelete, 'confirm-delete': deleteTask
    };
    if (actions[b.dataset.action]) actions[b.dataset.action](id);
  });

  // Escape cancels an edit or a pending deletion.
  list.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var id = e.target.closest('li') && e.target.closest('li').dataset.id;
    if (id && id === editingId) cancelEdit(id);
    else if (id && id === confirmingId) cancelDelete(id);
  });

  $('download-raw').addEventListener('click', downloadRaw);
  $('start-fresh').addEventListener('click', startFresh);

  // Another tab changed the saved tasks.
  window.addEventListener('storage', function (e) {
    var area; try { area = window.localStorage; } catch (err) { return; }
    if (e.storageArea !== area || (e.key !== null && e.key !== STORAGE_KEY) || storage !== 'ok') return;
    if (dirty) {
      announce('Another tab changed the saved tasks. This page has unsaved changes, so it was not updated.');
      return;
    }
    refreshFromStorage();
    render();
    announce('Tasks were updated in another tab.');
  });

  // Warn before leaving with work that was not saved.
  window.addEventListener('beforeunload', function (e) {
    if (dirty) { e.preventDefault(); e.returnValue = ''; }
  });

  /* ---------- Start ---------- */
  var first = load();
  storage = first.status; tasks = first.tasks; rawSaved = first.raw || null;
  render();
})();
