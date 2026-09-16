# CLAUDE.md

체육센터 입장권 웹 발권 시스템 (Flask + SQLite + BIXOLON SRP-350III). 사용법·API는 README.md, 요구사항은 `docs/웹 영수증 발권 시스템 프로젝트 계획서.docx`, 영수증 레이아웃 기준은 `docs/영수증 출력 양식.pdf`.

## 실행 / 확인

```bash
.venv/bin/python app.py                                   # http://127.0.0.1:5000 (실제 인쇄됨)
TICKET_DRY_RUN=1 TICKET_DB=/tmp/t.db .venv/bin/python app.py   # 인쇄 없이 output/*.png, 테스트 DB
.venv/bin/python tools/print_samples.py --preview         # 양식 예시 6장 -> output/samples_preview.png
```

- 테스트나 개발 중에는 `TICKET_DRY_RUN=1`과 별도 `TICKET_DB`를 쓴다. 실제 인쇄는 용지를 소모하고, 기본 `receipt.db`에는 실제 발권 기록이 쌓인다.
- 레이아웃을 바꾸면 `print_samples.py --preview` 이미지를 양식 PDF와 비교한다.
- 이 개발 PC(Ubuntu 24.04)에는 `ensurepip`이 없다. venv는 `python3 -m venv --without-pip .venv`로 만들고, 패키지는 `python3 -m pip --python .venv/bin/python install -r requirements.txt`로 설치한다.

## 프린터 사실관계 (개발 PC에서 확인됨)

- CUPS 큐 이름: `SRP-350III`. BIXOLON 공식 CUPS 드라이버 v1.5.9가 설치돼 있다(PPD `Bixolon/SRP350III_v1.0.7.ppd`).
- 앱은 드라이버를 거치지 않고 `lp -o raw`로 ESC/POS를 보낸다: `ESC @` → `GS v 0` 래스터 → 급지 → `GS V 66 0` 부분 절단.
- 인쇄 폭은 512도트(72mm @ 180dpi)다. 한글과 이모지는 PC 폰트(Noto Sans CJK KR, `.ttc`의 index 1)로 이미지를 그려서 출력한다.
- 프린터 내장 한글(EUC-KR, `FS &`)이 되는지는 확인하지 못했다. 텍스트 모드로 바꾸기 전에 먼저 실물로 확인할 것.
- 개발 PC 사용자는 `lp` 그룹이 아니다. `/dev/usb/lp*`에 직접 쓸 수 없으니 CUPS를 통해서만 보낸다.
- USB가 순간적으로 끊기면 CUPS 큐가 "Unplugged or turned off"로 비활성화된다. 이때는 `cupsenable SRP-350III`로 다시 켠다.

## 설계 규칙

- QR에는 개인정보를 넣지 않고 발권번호(`TICKET-YYYYMMDD-NNNNNN`)만 넣는다. 상세 정보는 `/api/tickets/<id>`로 조회한다.
- 발권 DB 기록과 인쇄는 한 트랜잭션으로 처리한다. 인쇄에 실패하면 기록도 롤백한다(`app.create_ticket`).
- 대기번호는 같은 날, 같은 시설·성별 안에서 1부터 증가한다. 상태값은 대기 `WAITING`, 정상 `ACTIVE`다.
- 양식에 따라 수영 입장권에는 QR을 넣지 않는다(`receipt.FACILITIES`). 계획서에는 "모든 발권에 QR"이라고 돼 있어서, 확정이 필요하면 사용자에게 확인한다.
- 회원명은 영수증에 가운데 글자를 가려서 출력한다(`receipt.mask_name`). 관리 페이지에는 실명이 그대로 나온다.
- 개인정보를 보여 주는 라우트(`/admin`, `GET /api/tickets/<id>`)에는 반드시 `@admin_only`를 붙인다. 비밀번호가 없으면 localhost에서만 열린다.
- 시설을 추가할 때는 `receipt.FACILITIES`만 수정하면 된다. 화면 선택지와 입력 검증에 자동으로 반영된다.

## 진행 상황

- 완료: 계획서 12장 기준 1~7단계, 읽기 전용 관리 페이지 `/admin`
- 남음: 8단계(대기자 목록 화면, QR 스캔 확인 화면, 대기발권 → 정상발권 전환 API), 9단계(실제 프린터 반복 출력 안정성 테스트)
- 확인하지 못한 것: 웹 화면에서 실제로 인쇄한 결과물. 지금까지 실물로 확인한 것은 초기 ESC/POS 텍스트 테스트 영수증뿐이다.
