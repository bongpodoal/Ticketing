# Ticketing

SRP-350III 기반 웹 영수증 발권 및 출력 시스템.
체육시설 발권 PC에서 Flask 서버를 띄우고, 브라우저에서 입력한 정보로 BIXOLON SRP-350III에 입장권을 출력한다.

- 계획서: [docs/웹 영수증 발권 시스템 프로젝트 계획서.docx](docs/)
- 출력 양식: [docs/영수증 출력 양식.pdf](docs/)

## 구조

```
app.py            Flask 서버 (입력 검사, 발권, 미리보기, 발권 조회 API)
admin.py          관리 페이지 (로그인, 발권·회원 조회/수정/삭제, 비밀번호 변경)
receipt.py        입력값 -> 영수증 이미지 (양식 레이아웃, 한글 폰트)
printer.py        ESC/POS 래스터 전송 + 자동 절단 (Linux CUPS / Windows RAW)
database.py       SQLite: members, tickets / 발권번호·대기번호 발급
qr.py             QR 코드 생성
templates/index.html, static/style.css, static/script.js   발권 화면
templates/admin*.html, static/admin.css   관리 페이지 화면
tools/print_samples.py   양식의 예시 6장 출력
docs/             계획서, 출력 양식
```

`receipt.db`(DB)와 `instance/secret_key`(로그인 세션 서명 키)는 첫 실행 때 자동 생성된다(git 제외).

## 설치

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip install -r requirements.txt
```

Ubuntu에서 `ensurepip`이 없다고 나오면:

```bash
python3 -m venv --without-pip .venv
python3 -m pip --python .venv/bin/python install -r requirements.txt
```

### 프린터

- **Linux:** BIXOLON 공식 CUPS 드라이버를 설치하고 큐 이름을 `SRP-350III`로 등록한다. 영수증은 드라이버를 거치지 않고 `lp -o raw`로 ESC/POS 데이터를 보낸다.
- **Windows:** BIXOLON Windows 드라이버를 설치한다. 프린터 이름이 다르면 `TICKET_PRINTER`에 지정한다.
- 한글은 프린터 내장 폰트가 아니라 PC 폰트로 그린 이미지로 출력한다. 기본 폰트는 Noto Sans CJK(Linux)와 맑은 고딕(Windows)이다.

## 실행

```bash
.venv/bin/python app.py
# 브라우저에서 http://127.0.0.1:5000
```

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `TICKET_PRINTER` | `SRP-350III` | 프린터(큐) 이름 |
| `TICKET_DRY_RUN` | – | `1`이면 인쇄하지 않고 `output/`에 PNG 저장 |
| `TICKET_DB` | `./receipt.db` | SQLite 파일 경로 |
| `TICKET_HOST` / `TICKET_PORT` | `127.0.0.1` / `5000` | 내부망 태블릿에서 접속하려면 `TICKET_HOST=0.0.0.0` |
| `TICKET_SECRET_KEY` | `instance/secret_key` | 로그인 세션 서명 키 |
| `TICKET_FONT_REGULAR` / `TICKET_FONT_BOLD` | – | 한글 폰트 파일 경로 지정 |

양식 예시 출력: `.venv/bin/python tools/print_samples.py` (`--preview`를 붙이면 `output/samples_preview.png`만 생성)

## 관리 페이지

http://127.0.0.1:5000/admin 에 접속하면 로그인 화면이 나온다. **초기 계정은 `admin` / `admin`**이다.

- **초기 비밀번호:** 바꾸기 전에는 화면 상단에 경고가 뜨고, 발권 PC(localhost)에서만 접속할 수 있다. [비밀번호 변경]에서 8자 이상으로 바꾸면 내부망의 다른 기기에서도 로그인할 수 있다.
- **발권 기록:**
  - 날짜·시설·상태로 필터하고, 발권번호·회원번호·이름으로 검색한다. [전체 기간]을 누르면 모든 날짜를 본다.
  - [수정]에서 시설·성별·상태·락카번호·대기번호·회원번호·이용료를 바꾸거나 기록을 삭제한다.
  - 대기자를 입장시킬 때는 상태를 `정상`으로 바꾸고 락카번호를 입력한다.
- **회원:**
  - 회원을 등록·수정·삭제한다. 회원번호는 수정할 수 없다.
  - 발권 기록이 남아 있는 회원은 삭제할 수 없다.
- **보안:** 비밀번호는 해시로만 저장한다(`admins` 테이블). 모든 수정 요청에는 CSRF 토큰을 확인한다. 로그인에 실패하면 1초씩 늦게 응답한다.
- **비밀번호 분실:** 서버를 멈추고 `sqlite3 receipt.db "DELETE FROM admins"`를 실행한 뒤 서버를 다시 켜면 `admin`/`admin`으로 초기화된다.

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/api/tickets` | 발권: DB 저장 후 인쇄. 인쇄에 실패하면 DB 기록도 롤백 |
| `POST` | `/api/preview` | 영수증 PNG만 생성 (DB 저장·인쇄 없음) |
| `GET` | `/api/tickets/<ticket_id>` | QR로 스캔한 발권번호의 상태 조회 (관리자 로그인 필요, 아니면 401) |
| `GET` | `/admin` | 관리 페이지 (로그인 필요) |

요청 본문(JSON): `entry_type`(member/daily), `facility`(헬스1/헬스2/수영), `gender`(남자/여자), `issue_type`(normal/waiting), `locker`(정상발권), `member_id`·`member_name`·`start_date`·`end_date`(회원), `fee`(일일)

## 동작 규칙

- 발권번호: `TICKET-YYYYMMDD-000001`, 날짜마다 1부터 증가. QR에는 개인정보 대신 이 번호만 담는다.
- 대기번호: 같은 날, 같은 시설·성별 안에서 1부터 증가. 상태는 `WAITING`이다. 정상발권의 상태는 `ACTIVE`다.
- 회원명은 영수증에 가운데 글자를 가려서 출력한다 (`이상재` → `이*재`).
- 양식에 맞춰 수영 입장권에는 QR을 출력하지 않는다 (`receipt.FACILITIES`에서 변경).

## 진행 상황 (계획서 12장 기준)

- [x] 1단계 개발환경, 드라이버 설치, 테스트 출력
- [x] 2~6단계 웹페이지, Flask 연결, 입력 검증, 영수증 양식, 한글·큰 글씨·자동 절단, QR, 발권번호
- [x] 7단계 회원·발권 기록 저장, 대기번호 발급
- [ ] 8단계 대기자 목록 화면, QR 스캔 확인 화면, 대기발권 → 정상발권 전환
- [ ] 9단계 실제 프린터 반복 출력 안정성 테스트
