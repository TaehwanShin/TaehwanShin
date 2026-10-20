---
name: rap-srvd-to-insomnia
description: ABAP RAP 서비스 정의(SRVD)로부터 Insomnia 컬렉션을 생성한다. SRVD와 (있으면) CDS 프로젝션 뷰·BDEF 소스를 파싱해 OData V4/V2 요청(조회, 생성, 수정, 삭제, 액션, draft Edit/Activate, CSRF 토큰 체이닝)을 만들고 insomnia MCP로 Insomnia 앱에 넣는다. "SRVD로 Insomnia 컬렉션 만들어줘", "RAP 서비스 테스트 요청 생성", "service definition → insomnia" 같은 요청에 사용.
---

# RAP SRVD → Insomnia 컬렉션

SRVD 소스 하나로 서비스 바인딩 URL, 엔티티별 CRUD, 액션, draft 요청이 들어간 Insomnia V4 컬렉션을 만든다.
생성은 결정적 스크립트(`scripts/srvd2insomnia.py`, Python 표준 라이브러리만 사용)가 하고,
Insomnia 반영은 insomnia MCP(`mcp-insomnia`, 저장소 루트 `.mcp.json`에 등록)가 한다.

## 1. 입력 수집

사용자에게 받거나 저장소에서 찾는다 (abapGit 파일명 규칙):

| 소스 | abapGit 파일 | 필수 |
|---|---|---|
| 서비스 정의 | `<name>.srvd.srvdsrv` | 필수 |
| CDS 프로젝션 뷰 | `<name>.ddls.asddls` | 키 필드를 알려면 필요 |
| 동작 정의(프로젝션/인터페이스) | `<name>.bdef.asbdef` | 없으면 GET만 생성 |

소스를 채팅에 붙여넣으면 scratchpad에 위 이름으로 저장해서 쓴다.
네임스페이스 객체(`/DMO/...`)는 abapGit에서 `#dmo#...`로 저장되는데, 스크립트가 이를 인식한다.

다음 값도 확인한다. 모르면 기본값을 쓰고 사용자에게 그렇게 했다고 알린다:

- **서비스 바인딩 이름**: 기본값은 SRVD 이름. 보통 `ZUI_..._O4`/`_O2`처럼 SRVD와 다르므로 꼭 물어본다.
- **OData 버전**: `v4`(기본) 또는 `v2`
- **바인딩 유형**: `ui`(UI 서비스, `/srvd/`, 기본) 또는 `api`(Web API, `/srvd_a2x/`)
- **서비스 버전**: 기본 `0001`
- **호스트 URL**, **SAP 클라이언트**: 선택. 없으면 환경 변수 자리표시자가 들어간다.

## 2. spec 생성 후 검토

```bash
python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/srvd2insomnia.py \
  --srvd <srvd 파일> --src-dir <CDS/BDEF 폴더> \
  --binding <바인딩> --odata v4 --binding-type ui \
  --base-url https://<host>:<port> --sap-client 100 \
  --dump-spec <scratchpad>/spec.json
```

stderr 경고(키를 모름, BDEF 없음 등)를 읽고 `spec.json`을 직접 고친다. 파서는 휴리스틱 방식이라 아래 항목은 꼭 확인한다:

- `keys[].type`: `guid` | `string` | `number`. 이 값으로 키 리터럴이 정해진다. V4는 guid/number에 따옴표를 붙이지 않고 string에는 `'..'`를 붙인다. V2는 `guid'..'`를 쓴다.
  이름이 `UUID`로 끝나면 guid로 추정한다. 숫자형(NUMC가 아닌 INT 등) 키는 `number`로 바꾼다.
- `root`, `draft`, `create`/`update`/`delete`, `actions`, `createByAssociation`, `associations`
- CDS 소스가 없는 값 도움말용 엔티티는 `keys`가 비어 있으면 목록 조회(List)만 생성된다.

## 3. Insomnia export 렌더링

```bash
python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/srvd2insomnia.py \
  --spec <scratchpad>/spec.json -o <scratchpad>/<binding>.insomnia.json
```

`--binding`, `--odata`, `--binding-type`, `--service-version`, `--base-url`, `--sap-client`를 주면 spec 값보다 우선한다.
ID는 서비스/폴더/요청 이름의 해시로 만든다. 그래서 다시 생성하면 같은 컬렉션이 중복되지 않고 갱신된다.

생성되는 구조:

- `00 Service`: **Fetch CSRF token**(`X-CSRF-Token: Fetch`), `$metadata`
- `NN <Entity>`: List(`$top`, `$count`/`$inlinecount`), Read by key, 연관 탐색, Create, Create via `_assoc`,
  Update(PATCH), Delete, 액션/함수. draft 루트에는 Edit / Activate / Prepare / Discard draft도 생성한다.
- 모든 요청에 Basic 인증(`{{ _.username }}`/`{{ _.password }}`)과 `sap-client` 쿼리를 넣는다.
- 변경 요청의 `X-CSRF-Token`은 Fetch 요청 응답 헤더를 읽는 response 태그다(10분 지나면 다시 받음). 세션 쿠키는 워크스페이스 쿠키 저장소가 유지한다.
- draft가 켜진 엔티티는 Update와 자식 Delete가 `IsActiveEntity=false` draft 인스턴스를 대상으로 한다.
- V4 액션 경로: `<Entity>(<keys>)/com.sap.gateway.srvd.<srvd>.v<버전>.<action>` (static 액션은 컬렉션에 바인딩).
- V2 액션/draft는 function import(`/<action>?<keys>`, `/<Entity>Edit` 등)로 생성한다. 이름에 접두사가 붙는 경우가 있으니 `$metadata`로 확인하라고 알린다.

## 4. insomnia MCP로 반영

`mcp__insomnia__*` 도구가 없으면 ToolSearch로 `insomnia`를 검색한다. 그래도 없으면 `.mcp.json`이 승인됐는지 확인하라고 안내한다(`/mcp`).
도구를 아예 쓸 수 없으면 5단계 파일 import로 넘어간다.

1. `import_from_insomnia_export` { filePath: 생성한 JSON의 **절대 경로** }: MCP 저장소(`~/.mcp-insomnia`)에 등록
2. `list_collections`로 워크스페이스 ID(`wrk_...`) 확인
3. 로컬 Insomnia 앱에 넣을 때:
   - `list_insomnia_projects`로 프로젝트 ID를 확인한다. `projectId`는 **항상 명시**한다. 생략하면 존재하지 않는 `proj_default`에 들어갈 수 있다.
   - `sync_to_insomnia` { collectionId, projectId, dryRun: true }로 먼저 변경 내용을 보여준다.
   - 사용자 확인 뒤 **Insomnia 앱을 종료한 상태에서** `sync_to_insomnia` { collectionId, projectId, backup: true }를 실행한다. MCP가 Insomnia NeDB 파일에 직접 쓰기 때문에 앱이 켜져 있으면 덮어써질 수 있다. 끝나면 Insomnia를 다시 시작하라고 안내한다.
   - "Insomnia data directory not found"가 나오면 Insomnia가 없는 환경(클라우드 세션 등)이다. `INSOMNIA_DATA_DIR`로 경로를 지정하거나 5단계로 넘어간다.
4. 시스템에 접속할 수 있고 사용자가 원하면 `execute_request`로 `Fetch CSRF token`과 `$metadata`를 실행한다. 엔티티 셋, 액션 이름, 키 타입이 실제와 맞는지 확인하고, 다르면 spec을 고쳐 3단계부터 다시 한다.
   (MCP 실행기는 Insomnia response 태그를 해석하지 못할 수 있다. 변경 요청은 Insomnia 앱에서 실행하라고 안내한다.)

## 5. 마무리 안내

- 생성 파일 경로, 요청 개수, 경고, 직접 채워야 할 값을 알려준다.
  채울 값: 환경 변수 `baseUrl`, `sap_client`, `username`, `password`, `<Entity>_<Key>`, 요청 본문 `<Field>` 자리표시자.
- MCP를 쓰지 못한 경우: Insomnia → **Import** → 생성한 JSON 파일을 선택하면 된다.
- 비밀번호는 파일에 쓰지 않는다. 사용자가 Insomnia 환경에서 직접 입력하게 한다.

## 참고

- 예제 소스: `examples/` (draft가 켜진 Travel/Booking, V4 UI 서비스)
  ```bash
  python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/srvd2insomnia.py \
    --srvd .claude/skills/rap-srvd-to-insomnia/examples/zui_travel.srvd.srvdsrv \
    --src-dir .claude/skills/rap-srvd-to-insomnia/examples -o <scratchpad>/travel.json
  ```
- 매칭 규칙: SRVD의 `expose <CDS> as <Alias>`에서 CDS 이름으로 CDS 소스와 BDEF(`define behavior for <CDS>`)를 찾는다.
  같은 엔티티에 프로젝션 BDEF와 인터페이스 BDEF가 둘 다 있으면 프로젝션 BDEF를 우선한다.
  액션 파라미터 구조는 인터페이스 BDEF에서 가져온다. `internal` 동작과 draft 액션 선언은 일반 액션 목록에서 뺀다.
