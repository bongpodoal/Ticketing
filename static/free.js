const form = document.getElementById("free-form");
const text = form.elements.text;
const count = document.getElementById("count");
const message = document.getElementById("message");
const printBtn = document.getElementById("print-btn");
const previewBtn = document.getElementById("preview-btn");
const previewBox = document.getElementById("preview");
const previewImg = document.getElementById("preview-img");

function showMessage(msg, kind) {
  message.textContent = msg;
  message.className = kind;
}

async function post(url) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(Object.fromEntries(new FormData(form))),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: `서버 오류 (${res.status})` }));
    throw new Error(err.error);
  }
  return res;
}

text.addEventListener("input", () => {
  count.textContent = text.value.length;
});

previewBtn.addEventListener("click", async () => {
  try {
    const res = await post("/api/free/preview");
    if (previewImg.src) URL.revokeObjectURL(previewImg.src);
    previewImg.src = URL.createObjectURL(await res.blob());
    previewBox.hidden = false;
    showMessage("", "");
  } catch (e) {
    showMessage(e.message, "error");
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  printBtn.disabled = true;
  showMessage("출력 중…", "");
  try {
    await post("/api/free/print");
    showMessage("출력 완료", "ok");
  } catch (e) {
    showMessage(e.message, "error");
  } finally {
    printBtn.disabled = false;
  }
});
