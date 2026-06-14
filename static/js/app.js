document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) window.lucide.createIcons();

  const themeToggle = document.querySelector("#themeToggle");
  if (localStorage.getItem("careerai-theme") === "dark") document.body.classList.add("dark");
  themeToggle?.addEventListener("click", () => {
    document.body.classList.toggle("dark");
    localStorage.setItem("careerai-theme", document.body.classList.contains("dark") ? "dark" : "light");
  });

  document.querySelector(".copy-letter")?.addEventListener("click", async () => {
    const letter = document.querySelector("#letterText")?.textContent || "";
    await navigator.clipboard.writeText(letter);
  });

  let draggedCard = null;
  bindKanbanCards();
  document.querySelectorAll(".kanban-list").forEach((list) => {
    list.addEventListener("dragover", (event) => event.preventDefault());
    list.addEventListener("drop", async () => {
      if (draggedCard) {
        const status = list.closest(".kanban-col")?.dataset.status;
        const id = draggedCard.dataset.id;
        list.appendChild(draggedCard);
        updateKanbanCounts();
        if (id && status) {
          const response = await fetch(`/applications/${id}/status`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status }),
          });
          if (!response.ok) window.location.reload();
        }
      }
    });
  });

  document.querySelector("#addCardBtn")?.addEventListener("click", () => {
    document.querySelector("#addApplicationForm")?.classList.remove("hidden");
  });
  document.querySelector("#cancelAddBtn")?.addEventListener("click", () => {
    document.querySelector("#addApplicationForm")?.classList.add("hidden");
  });

  document.querySelector("#resumeFileInput")?.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    const label = document.querySelector("#resumeFileName");
    if (file && label) label.textContent = `Selected: ${file.name}`;
  });

  function bindKanbanCards() {
    document.querySelectorAll(".kanban-card").forEach((card) => {
      card.addEventListener("dragstart", () => {
        draggedCard = card;
        card.style.opacity = "0.45";
      });
      card.addEventListener("dragend", () => {
        card.style.opacity = "1";
        draggedCard = null;
      });
    });
  }
});

function updateKanbanCounts() {
  document.querySelectorAll(".kanban-col").forEach((column) => {
    const count = column.querySelectorAll(".kanban-card").length;
    const badge = column.querySelector("header b");
    if (badge) badge.textContent = count;
  });
}
