---
name: rap-srvd-to-insomnia
description: ABAP RAP 서비스 정의(SRVD)로부터 Insomnia 컬렉션을 생성한다. 컬렉션 이름을 입력받아 Setting(CSRF·$metadata·Fiori Elements Preview) / Get / Post 폴더 구조로 OData V4/V2 요청을 만든다. Post 요청에는 $metadata·CDS·BDEF에서 계산한 payload가 들어가고, Insomnia 형식 검증을 통과한 것만 내보낸다. base_url·service_path·sap_client·csrf_token은 환경 변수로 둔다. Insomnia 앱을 종료(task kill)한 뒤 insomnia MCP로 연동하고 다시 실행한다. "SRVD로 Insomnia 컬렉션 만들어줘", "RAP 서비스 테스트 요청 생성", "service definition → insomnia" 같은 요청에 사용.
---

# RAP SRVD → Insomnia 컬렉션

| 스크립트 (`scripts/`) | 역할 |
|---|---|
| `srvd2insomnia.py` | SRVD/CDS/BDEF/$metadata → spec → Insomnia V4 export (결정적, 표준 라이브러리만 사용) |
| `payload.py`, `edmx.py` | Edm 타입별 payload 생성, $metadata 파싱 (`srvd2insomnia.py`가 사용) |
| `insomnia_check.py` | Insomnia 형식 검증. 생성할 때 자동으로 실행되고, 따로 실행할 수도 있다 |
| `insomnia_app.py` | Insomnia 앱 종료/재시작 |

연동은 insomnia MCP(`mcp-insomnia`, 저장소 루트 `.mcp.json`)로 한다.

## 절대 규칙: payload는 손으로 만들지 않는다

LLM이 직접 쓴 Insomnia 요청 본문은 자주 깨진다. 아래는 실제로 겪은 문제다:

| 실수 | 결과 |
|---|---|
| `body: {"AgencyID": "1"}`처럼 payload 객체를 body에 그대로 넣음 | `sync_to_insomnia`가 `text: ''`로 바꿔서 **본문이 오류 없이 사라짐** |
| `body.text`에 문자열이 아닌 객체를 넣음 | 본문이 사라지거나 Insomnia가 읽지 못함 |
| `{"TotalPrice": {{ _.price }}}`처럼 따옴표 밖에 템플릿 태그 | Insomnia에서 JSON 오류 |
| 끝에 쉼표, 주석 등 JSON 문법 오류 | 요청 실패 |
| `Content-Type: application/json` 누락, `mimeType` 누락 | SAP가 본문을 읽지 못함 |
| `{{ base_url }}`(`_.` 없음), 존재하지 않는 변수 | 빈 값으로 전송됨 |
| header/parameter 행에 `id`가 없거나 중복 | Insomnia UI "Render Failure: Invalid array length" |
| OData 값 형식: V4는 `Edm.Date` `"2026-01-01"`, Decimal은 숫자. V2는 `"/Date(ms)/"`, Decimal·Int64는 문자열 | SAP가 400 응답 |

그래서:

- 요청과 payload는 **항상 `srvd2insomnia.py`로만 생성**한다. `create_request_in_collection` / `update_request` MCP 도구로 본문을 만들거나 고치지 않는다.
- 필드나 값을 바꾸려면 `spec.json`을 고친 뒤 다시 렌더링한다. ID가 고정되어 있어서 다시 연동하면 같은 요청이 갱신된다.
- 생성기는 검증에 실패하면 파일을 쓰지 않는다. 사용자가 준 export 파일이나 MCP `export_collection` 결과도 `insomnia_check.py <file>`로 검사할 수 있다.

## 컬렉션 구조

```
<컬렉션 이름>                       ← 사용자 입력
├─ Setting
│   ├─ Fetch CSRF token            GET service root, X-CSRF-Token: Fetch
│   ├─ $metadata
│   └─ Fiori Elements Preview      ADT 서비스 바인딩에서 Preview로 여는 테스트 페이지 ({{ _.preview_url }})
├─ Get                             <Entity> - List / Read by key / <연관>
└─ Post                            Create, Create via <연관>, Create (deep), Update(PATCH), Delete,
                                   Draft Edit/Activate/Prepare, Discard draft, Action/Function
```

Post 요청에는 `X-CSRF-Token: {{ _.csrf_token }}`이 들어간다. PATCH와 DELETE도 CSRF 토큰이 필요한 변경 요청이라 Post에 넣는다.

### URL과 환경 변수

모든 요청 URL은 `{{ _.base_url }}{{ _.service_path }}/<EntitySet>...` 형태다.

| 변수 | 값 |
|---|---|
| `base_url` | `https://<host>:<port>` (프로토콜 + 호스트 + 포트만) |
| `service_path` | 바인딩에서 계산한 서비스 경로. 바인딩이나 버전을 바꾸려면 이 값만 고치면 된다 |
| `sap_client` | 모든 요청의 `sap-client` 쿼리 |
| `csrf_token` | `Fetch CSRF token` 응답 헤더 `x-csrf-token`을 읽는 response 태그 (10분 지나면 다시 받음) |
| `preview_url` | Fiori Elements Preview 주소. 호스트는 `{{ _.base_url }}`, 클라이언트는 `{{ _.sap_client }}`로 바뀐다 |
| `username`, `password` | Basic 인증. 사용자가 Insomnia에서 직접 입력한다 |
| `<Entity>_<Key>` | 키 조회·변경 요청에 쓰는 키 값 |

`service_path` 규칙:

| 바인딩 | 경로 |
|---|---|
| OData V4 UI | `/sap/opu/odata4/sap/<binding 소문자>/srvd/sap/<srvd 소문자>/<버전>` |
| OData V4 Web API | `/sap/opu/odata4/sap/<binding 소문자>/srvd_a2x/sap/<srvd 소문자>/<버전>` |
| OData V2 | `/sap/opu/odata/sap/<BINDING>` |

## 1. 입력 수집

**컬렉션 이름은 반드시 사용자에게 물어본다.** 이름이 컬렉션 ID를 정한다. 같은 이름이면 기존 컬렉션이 갱신되고, 다른 이름이면 새 컬렉션이 생긴다.

| 소스 | abapGit 파일 | 쓰임 |
|---|---|---|
| 서비스 정의 | `<name>.srvd.srvdsrv` | 필수. 노출 엔티티 |
| CDS 프로젝션 뷰 | `<name>.ddls.asddls` | 키, 필드 목록, 연관(대상 포함) |
| 인터페이스/프로젝션 BDEF | `<name>.bdef.asbdef` | create/update/delete, 액션, draft, field control(readonly, mandatory, readonly : update, numbering : managed) |
| 액션 파라미터 abstract entity | `<name>.ddls.asddls` | 액션 payload 필드와 타입 |
| **서비스 `$metadata`** | XML 파일 | **payload 타입의 정답.** Edm 타입, 키, 읽기 전용(Computed/Immutable/sap:creatable), 필수 필드, 액션 파라미터, V2 function import 이름 |

`$metadata`가 있으면 payload가 정확해지므로 **가능하면 받는다.** 받는 방법:

1. 브라우저에서 `https://<host>:<port><service_path>/$metadata?sap-client=<client>`를 열고 다른 이름으로 저장
2. 컬렉션을 한 번 연동한 뒤 Insomnia에서 `Setting/$metadata`를 실행하고 응답을 파일로 저장
3. 시스템에 접속할 수 있으면 사용자가 허락한 경우 curl로 받는다. 비밀번호는 파일이나 명령 기록에 남기지 않는다.

`$metadata` 없이 먼저 만들었다면, 나중에 `--spec spec.json --metadata <file>`로 다시 렌더링하고 다시 연동한다.

**Fiori Elements Preview**(ADT 서비스 바인딩 → 엔티티 선택 → Preview, 브라우저 테스트 페이지): 사용자가 Preview를 한 번 눌러 열린 브라우저 주소를 복사해 주면 `--preview-url`로 넘긴다. 없으면 자리표시자가 들어가고, 나중에 Insomnia 환경의 `preview_url`에 붙여넣으면 된다. 주소 형식을 추측해서 만들지 않는다.

그 밖의 값(모르면 기본값을 쓰고 알린다):
- 서비스 바인딩 이름: 기본값은 SRVD 이름. 보통 다르므로 꼭 물어본다.
- OData `v4`/`v2`: `$metadata`가 있으면 거기서 정해진다.
- 바인딩 유형 `ui`/`api`, 서비스 버전 `0001`
- `base_url`, `sap_client`

## 2. spec 생성 후 검토

```bash
python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/srvd2insomnia.py \
  --srvd <srvd> --src-dir <CDS/BDEF 폴더> --metadata <metadata.xml> \
  --collection-name "<컬렉션 이름>" --binding <바인딩> --binding-type ui \
  --base-url https://<host>:<port> --sap-client 100 --preview-url '<ADT preview 주소>' \
  --dump-spec <scratchpad>/spec.json
```

stderr 경고를 읽고 `spec.json`을 확인한다:

- `entities[].fields[]`: `{name, edm, maxLength, key, mandatory, readonly, createOnly, typed}`
  - `readonly`: 어떤 요청에서도 보내지 않는다
  - `createOnly`: Create에서만 보낸다
  - `typed: false`: 타입을 추측한 필드. `$metadata` 없이 데이터 요소로 정의된 필드는 `Edm.String`이 된다. 날짜, 금액 등은 `edm`을 고친다(`Edm.Date`, `Edm.Decimal`, `Edm.Int32`, `Edm.Boolean`, `Edm.Guid`, `Edm.DateTimeOffset` 등).
  - UUID 키는 managed numbering으로 보고 보내지 않는다. 자식 엔티티의 부모 키 필드도 보내지 않는다.
- `actions[].params[]`: 액션 파라미터 `{name, edm}`
- `keys[].type`(`guid`/`number`/`string`), `root`, `draft`, `create`/`update`/`delete`, `createByAssociation`, `associationTargets`

## 3. 렌더링 (+ 자동 형식 검증)

```bash
python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/srvd2insomnia.py \
  --spec <scratchpad>/spec.json -o <scratchpad>/<컬렉션>.insomnia.json
```

출력 끝에 `format check ok`가 있어야 한다. 실패하면 오류 목록이 나오고 파일은 쓰지 않는다. 생성기 버그이므로 spec이나 코드를 고친다.

payload 규칙(`payload.py`):

| 요청 | 본문 |
|---|---|
| Create | 보낼 수 있는 필드 전체. 필수 필드가 먼저 온다. 문자열 키는 `"{{ _.<Entity>_<Key> }}"`를 따옴표 안에 넣는다 |
| Update(PATCH) | 수정 가능한 필드만 (키, readonly, createOnly 제외). 바꾸지 않을 필드는 빼라고 description에 적는다 |
| Create via 연관 | 자식 엔티티의 생성 필드 (부모 키 제외) |
| Create (deep), V4 | 루트 필드 + `"<_연관>": [ {자식 필드} ]` |
| V4 Action | 파라미터 객체. 파라미터가 없으면 `{}`. Draft Edit은 `{"PreserveChanges": true}` |
| V2 Action/Draft | 본문 없음. 키와 파라미터를 URL 리터럴(`guid'..'`, `0M`, `datetime'..'`)로 쿼리에 넣는다 |

V4 Edm 샘플 값: String `""`, Int `0`, Decimal `0`, Boolean `false`, Date `"2026-01-01"`, DateTimeOffset `"2026-01-01T00:00:00Z"`, Guid `"00000000-..."`.
V2에서 다른 점: DateTime `"/Date(1767225600000)/"`, Decimal·Int64·Double은 `"0"`(문자열).

각 Post 요청의 description에는 필드 안내(타입, 최대 길이, 필수 여부, 보내지 않는 필드)가 들어간다.

## 4. Insomnia 종료 → MCP 연동 → 재시작

mcp-insomnia는 Insomnia NeDB 파일에 직접 쓴다. 실행 중인 앱은 메모리의 데이터로 이 파일을 덮어쓰므로 **반드시 앱을 종료한 뒤 연동**한다.

`mcp__insomnia__*` 도구가 없으면 ToolSearch로 `insomnia`를 검색한다. 그래도 없으면 `/mcp` 승인 여부를 안내하고 5단계의 파일 import로 넘어간다.

1. `import_from_insomnia_export` { filePath: 생성한 JSON의 **절대 경로** }
2. 컬렉션 ID = 생성 JSON의 `resources[0]._id`(`wrk_...`)
3. `list_insomnia_projects`로 프로젝트 ID를 확인한다. `projectId`는 **항상 명시**한다(생략하면 `proj_default`에 들어갈 수 있다).
4. `sync_to_insomnia` { collectionId, projectId, dryRun: true }로 변경 내용을 보여준다.
5. 사용자가 확인하면 저장하지 않은 작업이 닫힌다고 알리고 앱을 종료한다:
   ```bash
   python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/insomnia_app.py stop
   ```
   정상 종료를 먼저 시도하고, 15초 안에 끝나지 않으면 강제 종료한다(Windows `taskkill /IM Insomnia.exe /T` → `/F`, macOS `quit app` → `pkill -9`, Linux `pkill -x insomnia` → `-9`). 프로세스 이름이 정확히 일치할 때만 종료하므로 mcp-insomnia(node)는 건드리지 않는다. 종료 코드가 1이면 연동하지 말고 사용자에게 직접 종료해 달라고 한다.
6. `sync_to_insomnia` { collectionId, projectId, backup: true } (백업 위치: `~/.mcp-insomnia/backups`)
7. 검증: `export_collection` { collectionId, filePath: <scratchpad>/roundtrip.json } → `insomnia_check.py <scratchpad>/roundtrip.json`. 생성 파일과 요청 수, Post 본문이 같은지 확인한다.
8. 앱을 다시 실행한다:
   ```bash
   python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/insomnia_app.py start   # 못 찾으면 --exe <경로>
   ```

"Insomnia data directory not found"가 나오면 Insomnia가 없는 환경이다. `INSOMNIA_DATA_DIR`로 경로를 지정하거나 5단계로 넘어간다.

## 5. 마무리 안내

- 생성 파일 경로, 요청 수(Setting/Get/Post), 경고, `typed: false` 필드가 남아 있는지 알려준다.
- Insomnia에서 채울 값: `base_url`, `sap_client`, `username`, `password`, `<Entity>_<Key>`, (자리표시자라면) `preview_url`, 문자열 필드 값
- 사용 순서: `Setting/Fetch CSRF token` → `Get` / `Post`
- MCP를 쓰지 못하면: Insomnia → **Import** → 생성한 JSON 파일 선택

## 참고

- 예제: `examples/` (draft가 켜진 Travel/Booking, field control, 액션 파라미터 abstract entity)
  - `metadata_v4.xml`, `metadata_v2.xml`: RAP가 생성하는 구조를 따라 손으로 만든 테스트용 `$metadata`. 실제 시스템 응답이 아니다.
  ```bash
  python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/srvd2insomnia.py \
    --srvd .claude/skills/rap-srvd-to-insomnia/examples/zui_travel.srvd.srvdsrv \
    --src-dir .claude/skills/rap-srvd-to-insomnia/examples \
    --metadata .claude/skills/rap-srvd-to-insomnia/examples/metadata_v4.xml \
    --collection-name "Travel" -o <scratchpad>/travel.json
  ```
- 매칭 규칙: SRVD `expose <CDS> as <Alias>` → CDS 소스, BDEF(`define behavior for <CDS>`), `$metadata` EntitySet(`<Alias>`).
  - 프로젝션 BDEF를 인터페이스 BDEF보다 우선한다. field control과 액션 파라미터는 `projection on <base>`의 인터페이스 BDEF에서 가져온다.
  - V2에서 RAP는 연관 `_X`를 `to_X`로 노출하는데, `$metadata`가 있으면 자동으로 맞춘다.
