(() => {
  const search = document.getElementById("candidateSearch");
  const filter = document.getElementById("statusFilter");
  const rows = [...document.querySelectorAll("#candidateTable tbody tr")];
  function update() {
    const q = (search?.value || "").toLowerCase().trim();
    const status = filter?.value || "";
    rows.forEach(row => {
      const matchesText = (row.dataset.search || "").includes(q);
      const matchesStatus = !status || row.dataset.status === status;
      row.hidden = !(matchesText && matchesStatus);
    });
  }
  search?.addEventListener("input", update);
  filter?.addEventListener("change", update);
})();
