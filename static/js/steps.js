/*
 * Шаги обучения: отметка «выполнено», автосохранение заметки, обновление прогресса и кнопки «Проверить знания».
 * Состояние рисует сервер; скрипт только отправляет изменения на /modules/<id>/steps/<step_id>/.
 */
(function () {
    'use strict';

    var NOTE_DEBOUNCE_MS = 700;

    function initSteps(root) {
        if (!root) return;
        var tokenInput = root.querySelector('input[name=csrfmiddlewaretoken]');
        var token = tokenInput ? tokenInput.value : '';
        var msg = function (name) { return root.getAttribute('data-msg-' + name) || ''; };

        function setStatus(card, state, text) {
            var el = card.querySelector('[data-step-status]');
            if (!el) return;
            el.setAttribute('data-state', state);
            el.textContent = text || '';
        }

        function applyDone(card, done) {
            card.setAttribute('data-done', done ? '1' : '0');
            var button = card.querySelector('[data-toggle]');
            if (!button) return;
            button.setAttribute('aria-pressed', done ? 'true' : 'false');
            var label = button.getAttribute(done ? 'data-label-done' : 'data-label-todo');
            if (label) { button.setAttribute('title', label); button.setAttribute('aria-label', label); }
        }

        function setOpen(card, open) {
            card.setAttribute('data-open', open ? '1' : '0');
            var expander = card.querySelector('[data-expand]');
            if (expander) expander.setAttribute('aria-expanded', open ? 'true' : 'false');
        }

        // Путь: выполненные — done, первый невыполненный — current, остальные — upcoming.
        // Если статус шага только что менялся, выполненный сворачивается, а новый текущий раскрывается.
        function refreshStates(changedCard) {
            var cards = Array.prototype.slice.call(root.querySelectorAll('[data-step]'));
            var current = cards.filter(function (c) { return c.getAttribute('data-done') !== '1'; })[0];
            cards.forEach(function (c) {
                var was = c.getAttribute('data-state');
                var state = c.getAttribute('data-done') === '1' ? 'done' : (c === current ? 'current' : 'upcoming');
                c.setAttribute('data-state', state);
                if (!changedCard) return;
                if (c === changedCard && state === 'done') setOpen(c, false);
                else if (state === 'current' && was !== 'current') setOpen(c, true);
            });
            return current;
        }

        // Всплывающая подсказка «+20 XP» / «Новый ранг: …»
        function toast(text, big) {
            var el = document.createElement('div');
            el.textContent = text;
            el.setAttribute('role', 'status');
            el.className = 'pointer-events-none fixed z-50 rounded-full px-4 py-2 font-semibold text-white shadow-lg ' +
                (big ? 'bg-amber-500 text-base' : 'bg-brand-600 text-sm');
            el.style.left = '50%';
            el.style.bottom = big ? '5.5rem' : '1.5rem';
            el.style.opacity = '0';
            el.style.transform = 'translateX(-50%) translateY(12px)';
            el.style.transition = 'opacity .35s, transform .35s';
            document.body.appendChild(el);
            requestAnimationFrame(function () {
                el.style.opacity = '1';
                el.style.transform = 'translateX(-50%) translateY(0)';
            });
            setTimeout(function () {
                el.style.opacity = '0';
                setTimeout(function () { el.remove(); }, 400);
            }, big ? 2800 : 1700);
        }

        function updateGame(data) {
            if (typeof data.xp !== 'number') return;
            document.querySelectorAll('[data-nav-xp], [data-nav-xp-copy]').forEach(function (el) { el.textContent = data.xp; });
            if (data.rank_name) document.querySelectorAll('[data-nav-rank]').forEach(function (el) { el.textContent = data.rank_name; });
            if (data.xp_delta > 0) toast('+' + data.xp_delta + ' XP', false);
            if (data.rank_up) setTimeout(function () { toast(msg('rankup') + ' ' + data.rank_name, true); }, 900);
        }

        function updateSummary(data) {
            updateGame(data);
            var count = document.getElementById('steps-count');
            if (count) count.textContent = data.done_count + ' / ' + data.total;
            var bar = document.getElementById('steps-bar');
            if (bar && data.total) bar.style.width = Math.round(100 * data.done_count / data.total) + '%';
            if (typeof data.overall_percent === 'number') {
                document.querySelectorAll('[data-nav-percent]').forEach(function (el) { el.textContent = data.overall_percent; });
                document.querySelectorAll('[data-nav-bar]').forEach(function (el) { el.style.width = data.overall_percent + '%'; });
                document.querySelectorAll('[data-nav-progressbar]').forEach(function (el) { el.setAttribute('aria-valuenow', data.overall_percent); });
            }
            document.querySelectorAll('[data-required-left]').forEach(function (el) { el.textContent = data.required_left; });
            document.querySelectorAll('[data-quiz-ready]').forEach(function (el) { el.classList.toggle('hidden', !data.quiz_ready); });
            document.querySelectorAll('[data-quiz-locked]').forEach(function (el) { el.classList.toggle('hidden', data.quiz_ready); });
        }

        function post(card, payload) {
            setStatus(card, 'saving', msg('saving'));
            return fetch(card.getAttribute('data-url'), {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
                body: JSON.stringify(payload)
            }).then(function (response) {
                return response.json().catch(function () { return {}; }).then(function (data) {
                    if (response.ok && data.ok) {
                        card.removeAttribute('data-dirty');
                        applyDone(card, data.done);
                        var current = refreshStates(payload.done !== undefined ? card : null);
                        updateSummary(data);
                        setStatus(card, 'saved', msg('saved'));
                        if (payload.done === true && current && current !== card) {
                            setTimeout(function () { current.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 200);
                        }
                        return true;
                    }
                    if (response.status === 422) {
                        setStatus(card, 'warn', msg('note-required'));
                        setOpen(card, true);
                        var note = card.querySelector('[data-note]');
                        if (note) note.focus();
                        return false;
                    }
                    setStatus(card, 'failed', msg('failed'));
                    return false;
                });
            }).catch(function () {
                card.setAttribute('data-dirty', '1');
                setStatus(card, 'offline', msg('offline'));
                return false;
            });
        }

        root.querySelectorAll('[data-step]').forEach(function (card) {
            var button = card.querySelector('[data-toggle]');
            var note = card.querySelector('[data-note]');
            var timer = null;
            var expander = card.querySelector('[data-expand]');

            if (expander) {
                expander.addEventListener('click', function () {
                    setOpen(card, card.getAttribute('data-open') !== '1');
                });
            }

            if (button) {
                button.addEventListener('click', function () {
                    var done = card.getAttribute('data-done') !== '1';
                    if (done && card.getAttribute('data-requires-note') === '1' && note && !note.value.trim()) {
                        setStatus(card, 'warn', msg('note-required'));
                        setOpen(card, true);
                        note.focus();
                        return;
                    }
                    clearTimeout(timer);
                    button.disabled = true;
                    var payload = { done: done };
                    if (note) payload.note = note.value;
                    post(card, payload).then(function () { button.disabled = false; });
                });
            }

            if (note) {
                note.addEventListener('input', function () {
                    clearTimeout(timer);
                    setStatus(card, 'saving', msg('saving'));
                    timer = setTimeout(function () { post(card, { note: note.value }); }, NOTE_DEBOUNCE_MS);
                });
                // Ушёл со страницы, не дождавшись паузы — заметку всё равно отправляем
                document.addEventListener('visibilitychange', function () {
                    if (document.visibilityState === 'hidden' && timer) {
                        clearTimeout(timer); timer = null;
                        fetch(card.getAttribute('data-url'), {
                            method: 'POST', credentials: 'same-origin', keepalive: true,
                            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
                            body: JSON.stringify({ note: note.value })
                        });
                    }
                });
            }
        });

        // Связь вернулась — досылаем заметки, которые не ушли
        window.addEventListener('online', function () {
            root.querySelectorAll('[data-step][data-dirty]').forEach(function (card) {
                var note = card.querySelector('[data-note]');
                if (note) post(card, { note: note.value });
            });
        });
    }

    window.initSteps = initSteps;
})();
