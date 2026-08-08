/* ===================================================================
   PLANTILLA CANVAS "REDISEÑO 3" (UTPL)
   Archivo de JS único Prefijo de proyecto: ed-
   -------------------------------------------------------------------
   JavaScript "vanilla" (sin librerías). Todo el código se ejecuta
   dentro del evento "load" mediante la función ccMain(). Cada bloque
   de inicialización está aislado con try/catch y es "defensivo":
   si la página de Canvas no contiene un componente, esa función
   simplemente no hace nada (no-op). Así el mismo archivo puede
   cargarse en TODAS las páginas del curso sin provocar errores.
   =================================================================== */

window.addEventListener('load', () => {

    /* ==========================================================================
    Ocultar menu de Canvas
    ============================================================================= */

    // document.body.classList.remove('course-menu-expanded');

    /* =====================================================================
       === TABS DE PRELIMINARES ===
       ===================================================================== */

    document.addEventListener("click", function (event) {
        const link = event.target.closest(".preliminary-tabs__label");

        if (!link) return;

        event.preventDefault();

        const preliminaryTabs = link.closest(".preliminary-tabs");
        const tabContent = preliminaryTabs.querySelector("#" + link.dataset.tab);
        const isActive = link.classList.contains("is-active");

        // Si el tab seleccionado ya está abierto, se cierra.
        if (isActive) {
            link.classList.remove("is-active");
            link.setAttribute("aria-selected", "false");
            tabContent.classList.remove("is-active");
            return;
        }

        // Cierra todos los tabs y sus contenidos.
        preliminaryTabs.querySelectorAll(".preliminary-tabs__label").forEach(function (item) {
            item.classList.remove("is-active");
            item.setAttribute("aria-selected", "false");
        });

        preliminaryTabs.querySelectorAll(".preliminary-tabs__content").forEach(function (item) {
            item.classList.remove("is-active");
        });

        // Abre el tab seleccionado.
        link.classList.add("is-active");
        link.setAttribute("aria-selected", "true");
        tabContent.classList.add("is-active");
    });


    /* =====================================================================
       === COLLAPSE ===
       ===================================================================== */

    const collapse = document.querySelector(".collapse");
    const link = collapse.querySelector(".collapse__link");

    link.addEventListener("click", (event) => {
        event.preventDefault();

        const activo = collapse.classList.toggle("active");
        link.setAttribute("aria-expanded", activo);
    });

    link.addEventListener("keydown", (event) => {
        if (event.key === " ") {
            event.preventDefault();
            link.click();
        }
    });

    /* =====================================================================
      === TAB TOPICS ===
      ===================================================================== */

    document.addEventListener('click', function (e) {
        var tab = e.target.closest('.ctab__tab');
        if (!tab) return;
        var root = tab.closest('.ctab');
        root.querySelectorAll('.ctab__tab').forEach(function (t) { t.classList.remove('is-active'); });
        root.querySelectorAll('.ctab__panel').forEach(function (p) { p.classList.remove('is-active'); });
        tab.classList.add('is-active');
        var panel = root.querySelector('#' + tab.dataset.target);
        if (panel) panel.classList.add('is-active');
    });
});