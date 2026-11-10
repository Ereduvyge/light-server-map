/* Desktop layout is local to this browser; HTMX owns all server-rendered content. */
(() => {
    "use strict";

    const grid = document.querySelector("#node-grid");
    const dialog = document.querySelector("#software-dialog");
    const content = document.querySelector("#software-content");
    const error = document.querySelector("#request-error");
    const desktop = window.matchMedia("(min-width: 720px)");
    const storageKey = "light-server-map:positions:v1";
    let positions = {};
    let drag = null;
    let pendingNode = null;
    let requestingButton = null;
    let openerId = null;

    if (!window.htmx) {
        error.textContent = "Could not load interactive controls. Check CDN access and reload.";
        error.hidden = false;
    }

    try {
        const stored = JSON.parse(localStorage.getItem(storageKey) || "{}");
        if (stored && typeof stored === "object" && !Array.isArray(stored)) {
            positions = stored;
        }
    } catch {
        // Layout still works when browser storage is unavailable.
    }

    function savePositions() {
        try {
            localStorage.setItem(storageKey, JSON.stringify(positions));
        } catch {
            // Private browsing or a storage quota must not break dragging.
        }
    }

    function setPosition(card, x, y) {
        const maxX = Math.max(0, grid.clientWidth - card.offsetLeft - card.offsetWidth);
        const maxY = Math.max(0, grid.clientHeight - card.offsetTop - card.offsetHeight);
        x = Math.min(maxX, Math.max(-card.offsetLeft, x));
        y = Math.min(maxY, Math.max(-card.offsetTop, y));
        card.style.setProperty("--drag-x", `${x}px`);
        card.style.setProperty("--drag-y", `${y}px`);
        positions[card.dataset.nodeId] = { x, y };
    }

    function restorePositions() {
        grid.classList.remove("layout-ready");
        if (desktop.matches) {
            grid.querySelectorAll(".node-card").forEach((card) => {
                const point = positions[card.dataset.nodeId];
                if (point && Number.isFinite(point.x) && Number.isFinite(point.y)) {
                    setPosition(card, point.x, point.y);
                }
            });
        }
        // Paint restored positions before enabling hover/glow transitions.
        requestAnimationFrame(() => {
            requestAnimationFrame(() => grid.classList.add("layout-ready"));
        });
    }

    grid.addEventListener("pointerdown", (event) => {
        const handle = event.target.closest(".drag-handle");
        if (!handle || !desktop.matches || event.button !== 0) return;
        const card = handle.closest(".node-card");
        const point = positions[card.dataset.nodeId] || { x: 0, y: 0 };
        drag = { card, handle, pointer: event.pointerId, startX: event.clientX,
            startY: event.clientY, x: point.x, y: point.y };
        handle.setPointerCapture(event.pointerId);
        card.classList.add("is-dragging");
        event.preventDefault();
    });

    grid.addEventListener("pointermove", (event) => {
        if (!drag || event.pointerId !== drag.pointer) return;
        setPosition(drag.card, drag.x + event.clientX - drag.startX,
            drag.y + event.clientY - drag.startY);
    });

    function endDrag() {
        if (!drag) return;
        drag.card.classList.remove("is-dragging");
        if (drag.handle.hasPointerCapture(drag.pointer)) {
            drag.handle.releasePointerCapture(drag.pointer);
        }
        drag = null;
        savePositions();
    }

    grid.addEventListener("pointerup", endDrag);
    grid.addEventListener("pointercancel", endDrag);
    grid.addEventListener("lostpointercapture", endDrag);

    grid.addEventListener("keydown", (event) => {
        const directions = { ArrowLeft: [-16, 0], ArrowRight: [16, 0],
            ArrowUp: [0, -16], ArrowDown: [0, 16] };
        if (!event.target.matches(".drag-handle") || !desktop.matches || !directions[event.key]) return;
        event.preventDefault();
        const card = event.target.closest(".node-card");
        const point = positions[card.dataset.nodeId] || { x: 0, y: 0 };
        const [dx, dy] = directions[event.key];
        setPosition(card, point.x + dx, point.y + dy);
        savePositions();
    });

    document.addEventListener("htmx:beforeRequest", (event) => {
        if (drag && event.detail.target === grid) {
            event.preventDefault();
            return;
        }
        const element = event.detail.elt;
        if (element.matches(".node-button")) {
            pendingNode = element.dataset.openSoftware;
            openerId = pendingNode;
            requestingButton = element;
        }
    });

    document.addEventListener("htmx:afterSwap", (event) => {
        if (event.detail.target === grid) restorePositions();
        if (event.detail.target === content) {
            const panel = content.querySelector("#software-panel");
            if (panel && panel.dataset.nodeId === pendingNode && !dialog.open) {
                dialog.showModal();
            }
        }
    });

    document.addEventListener("htmx:afterRequest", (event) => {
        error.hidden = event.detail.successful;
    });

    dialog.addEventListener("close", () => {
        pendingNode = null;
        if (requestingButton) window.htmx.trigger(requestingButton, "htmx:abort");
        requestingButton = null;
        content.replaceChildren();
        document.querySelector(`#node-${openerId} .node-button`)?.focus({ preventScroll: true });
    });

    dialog.querySelector("[data-close-dialog]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
        const rect = dialog.getBoundingClientRect();
        if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right ||
            event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
    });

    document.querySelector("#reset-layout").addEventListener("click", () => {
        positions = {};
        grid.querySelectorAll(".node-card").forEach((card) => {
            card.style.removeProperty("--drag-x");
            card.style.removeProperty("--drag-y");
        });
        savePositions();
    });

    window.addEventListener("resize", restorePositions);
    restorePositions();
})();
