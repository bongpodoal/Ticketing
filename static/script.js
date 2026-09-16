const form = document.getElementById("ticket-form");
const message = document.getElementById("message");
const printBtn = document.getElementById("print-btn");
const previewBtn = document.getElementById("preview-btn");
const previewBox = document.getElementById("preview");
const previewImg = document.getElementById("preview-img");

// 선택값에 따라 입력칸 표시/숨김: data-for 가 선택된 entry_type 또는 issue_type 과 같을 때만 표시
function updateFields() {
  const data = new FormData(form);
  const active = [data.get("entry_type"), data.get("issue_type")];
  form.querySelectorAll("[data-for]").forEach((el) => {
    el.hidden = !active.includes(el.dataset.for);
  });
}

function payload() {
  const data = Object.fromEntries(new FormData(form));
  // 숨겨진 칸의 값은 보내지 않음
  form.querySelectorAll("[data-for][hidden] input").forEach((input) => delete data[input.name]);
  return data;
}

function showMessage(text, kind) {
  message.textContent = text;
  message.className = kind;
}

async function post(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: `서버 오류 (${res.status})` }));
    throw new Error(err.error);
  }
  return res;
}

form.addEventListener("change", updateFields);

previewBtn.addEventListener("click", async () => {
  try {
    const res = await post("/api/preview", payload());
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
    const res = await post("/api/tickets", payload());
    const t = await res.json();
    const label = t.issue_type === "waiting" ? "대기번호" : "락카번호";
    showMessage(`발권 완료: ${label} ${t.number} (${t.ticket_id})`, "ok");
    form.querySelector("[name=locker]").value = "";
  } catch (e) {
    showMessage(e.message, "error");
  } finally {
    printBtn.disabled = false;
  }
});

updateFields();
