/*
 * Автосохранение ответов на сервер.
 *  - каждое изменение уходит на сервер через ~0,5 с (радиокнопки и текстовые поля);
 *  - если связи нет — копия лежит в localStorage и отправляется при появлении связи
 *    или при следующем открытии страницы;
 *  - при закрытии/сворачивании вкладки несохранённое отправляется сразу;
 *  - состояние показывается в элементе [data-save-status].
 * Восстановление при открытии страницы делает сервер (он сам рисует отмеченные ответы),
 * поэтому обновление страницы и вход с другого устройства ничего не теряют.
 */
(function () {
    'use strict';

    var DEBOUNCE_MS = 500;
    var RETRY_MIN_MS = 3000;
    var RETRY_MAX_MS = 30000;

    function initAutosave(cfg) {
        var form = cfg.form;
        var statusEl = cfg.statusEl;
        var prefix = cfg.prefix;
        var tokenInput = form.querySelector('input[name=csrfmiddlewaretoken]');
        var token = tokenInput ? tokenInput.value : '';
        var msg = function (name) { return (statusEl && statusEl.getAttribute('data-msg-' + name)) || ''; };

        var timer = null, retryTimer = null, retryDelay = RETRY_MIN_MS;
        var failedToSend = false, sending = false, stopped = false;

        function setStatus(state, time) {
            if (!statusEl) return;
            statusEl.setAttribute('data-state', state);
            statusEl.textContent = msg(state) + (time ? ' ' + time : '');
        }

        function fields() {
            return form.querySelectorAll('input[type=radio], textarea');
        }

        function collect() {
            var answers = {};
            fields().forEach(function (el) {
                if (!el.name || el.name.indexOf(prefix) !== 0) return;
                var id = el.name.slice(prefix.length);
                if (el.type === 'radio') { if (el.checked) answers[id] = el.value; }
                else if (el.value.trim() !== '') { answers[id] = el.value; }
            });
            return answers;
        }

        function readLocal() {
            try { return JSON.parse(localStorage.getItem(cfg.storageKey)); } catch (e) { return null; }
        }
        function writeLocal(answers) {
            try { localStorage.setItem(cfg.storageKey, JSON.stringify({ ts: Date.now(), answers: answers })); } catch (e) {}
        }
        function clearLocal() {
            try { localStorage.removeItem(cfg.storageKey); } catch (e) {}
        }

        function applyToForm(answers) {
            fields().forEach(function (el) {
                if (!el.name || el.name.indexOf(prefix) !== 0) return;
                var id = el.name.slice(prefix.length);
                if (el.type === 'radio') { el.checked = String(answers[id]) === el.value; }
                else { el.value = answers[id] || ''; }
            });
            if (cfg.onRestore) cfg.onRestore();
        }

        function scheduleRetry() {
            clearTimeout(retryTimer);
            retryTimer = setTimeout(function () { send(false); }, retryDelay);
            retryDelay = Math.min(retryDelay * 2, RETRY_MAX_MS);
        }

        function send(keepalive) {
            if (stopped) return Promise.resolve();
            clearTimeout(timer); timer = null;
            clearTimeout(retryTimer);
            var answers = collect();
            var body = JSON.stringify({ answers: answers });
            sending = true;
            setStatus('saving');

            return fetch(cfg.url, {
                method: 'POST',
                credentials: 'same-origin',
                keepalive: !!keepalive && body.length < 60000,
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
                body: body
            }).then(function (response) {
                sending = false;
                if (response.ok) {
                    return response.json().then(function (data) {
                        failedToSend = false;
                        retryDelay = RETRY_MIN_MS;
                        // если пока шёл запрос ученик ещё что-то изменил — сохранит следующий цикл
                        if (JSON.stringify(collect()) === JSON.stringify(answers)) clearLocal();
                        setStatus('saved', data.saved_at);
                    });
                }
                if (response.status >= 500) throw new Error('server');
                // 4xx (сессия истекла, модуль закрыт…) — повторять бессмысленно
                writeLocal(answers);
                failedToSend = true;
                setStatus('failed');
            }).catch(function () {
                sending = false;
                failedToSend = true;
                writeLocal(answers);
                setStatus('offline');
                scheduleRetry();
            });
        }

        function schedule() {
            if (stopped) return;
            clearTimeout(timer);
            setStatus('saving');
            timer = setTimeout(function () { send(false); }, DEBOUNCE_MS);
        }

        form.addEventListener('input', schedule);
        form.addEventListener('change', schedule);

        // Отправка формы: больше ничего не сохраняем, защищаемся от двойного клика
        form.addEventListener('submit', function (event) {
            if (event.defaultPrevented) return;
            stopped = true;
            clearTimeout(timer); clearTimeout(retryTimer);
            clearLocal();
            form.querySelectorAll('button[type=submit]').forEach(function (button) {
                button.disabled = true;
                button.classList.add('opacity-60', 'cursor-not-allowed');
            });
        });

        // Ушёл со страницы / свернул вкладку — отправляем несохранённое немедленно
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'hidden' && (timer || failedToSend)) send(true);
        });
        window.addEventListener('pagehide', function () {
            if (timer || failedToSend) send(true);
        });
        window.addEventListener('online', function () { if (failedToSend) send(false); });
        window.addEventListener('beforeunload', function (event) {
            if (failedToSend && !stopped) { event.preventDefault(); event.returnValue = ''; }
        });

        // «Назад» из кэша браузера после отправки: перезагружаем, чтобы увидеть актуальное состояние
        window.addEventListener('pageshow', function (event) { if (event.persisted) location.reload(); });

        // Старт: если в прошлый раз связь оборвалась — досылаем то, что осталось на устройстве
        var pending = readLocal();
        if (pending && pending.answers && Object.keys(pending.answers).length) {
            applyToForm(pending.answers);
            send(false);
        } else if (cfg.restored) {
            setStatus('restored', cfg.savedAt);
        } else {
            setStatus('idle');
        }

        return { flush: function () { return send(false); } };
    }

    window.initAutosave = initAutosave;
})();
