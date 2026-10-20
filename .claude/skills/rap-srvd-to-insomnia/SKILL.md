---
name: rap-srvd-to-insomnia
description: ABAP RAP 서비스 정의(SRVD)로부터 Insomnia 컬렉션을 생성한다. 컬렉션 이름을 입력받아 Setting(CSRF·metadata) / Get / Post 폴더 구조로 OData V4/V2 요청을 만들고, base_url·sap_client·csrf_token은 환경 변수로 둔다. Insomnia 앱을 종료(task kill)한 뒤 insomnia MCP로 연동하고 다시 실행한다. "SRVD로 Insomnia 컬렉션 만들어줘", "RAP 서비스 테스트 요청 생성", "service definition → insomnia" 같은 요청에 사용.
---

# RAP SRVD → Insomnia 컬렉션

SRVD 소스로 Insomnia V4 컬렉션을 만들어 로컬 Insomnia 앱에 연동한다.

- 생성: `scripts/srvd2insomnia.py` (결정적, Python 표준 라이브러리만 사용)
- 앱 종료/재시작: `scripts/insomnia_app.py`
- 연동: insomnia MCP(`mcp-insomnia`, 저장소 루트 `.mcp.json`)

## 컬렉션 구조

```
<컬렉션 이름>                      ← 사용자 입력
├─ Setting
│   ├─ Fetch CSRF token           GET  X-CSRF-Token: Fetch
│   └─ $metadata
├─ Get                            조회: <Entity> - List / Read by key / <_assoc>
└─ Post                           변경: Create, Create via _assoc, Update(PATCH), Delete,
                                  Draft Edit/Activate/Prepare, Discard draft, Action ...
                                  (모든 요청에 X-CSRF-Token: {{ _.csrf_token }})
```

Base Environment 변수:

| 변수 | 값 |
|---|---|
| `base_url` | `https://<host>:<port>` (모든 URL이 `{{ _.base_url }}/sap/opu/...`로 시작) |
| `sap_client` | SAP 클라이언트. 모든 요청의 `sap-client` 쿼리에 들어감 |
| `csrf_token` | `Setting/Fetch CSRF token` 응답 헤더 `x-csrf-token`을 읽는 response 태그 (10분 지나면 자동으로 다시 받음) |
| `username`, `password` | Basic 인증. 비어 있는 채로 생성되며 사용자가 Insomnia에서 직접 입력 |
| `<Entity>_<Key>` | 키 조회·변경 요청에 쓰는 키 값 |

PATCH/DELETE도 CSRF 토큰이 필요한 변경 요청이라 `Post` 폴더에 넣는다.

## 1. 입력 수집

**컬렉션 이름은 반드시 사용자에게 물어본다.** 이름이 컬렉션 ID를 정한다. 같은 이름으로 다시 생성하면 기존 컬렉션이 갱신되고, 다른 이름이면 새 컬렉션이 생긴다.

소스는 사용자에게 받거나 저장소에서 찾는다 (abapGit 파일명 규칙):

| 소스 | abapGit 파일 | 필수 |
|---|---|---|
| 서비스 정의 | `<name>.srvd.srvdsrv` | 필수 |
| CDS 프로젝션 뷰 | `<name>.ddls.asddls` | 키 필드를 알려면 필요 |
| 동작 정의(프로젝션/인터페이스) | `<name>.bdef.asbdef` | 없으면 Get 요청만 생성 |

소스를 채팅에 붙여넣으면 scratchpad에 위 이름으로 저장해서 쓴다. 네임스페이스 객체(`/DMO/...`)의 abapGit 파일명 `#dmo#...`도 인식한다.

다음 값도 확인한다. 모르면 기본값을 쓰고 그렇게 했다고 알린다:

- **서비스 바인딩 이름**: 기본값은 SRVD 이름. 보통 `ZUI_..._O4`처럼 SRVD와 다르므로 꼭 물어본다.
- **OData 버전**: `v4`(기본) / `v2`
- **바인딩 유형**: `ui`(`/srvd/`, 기본) / `api`(Web API, `/srvd_a2x/`)
- **서비스 버전**: 기본 `0001`
- **base_url**, **sap_client**: 환경 변수 초기값. 없으면 `https://<host>:<port>`, `100`이 들어간다.

## 2. spec 생성 후 검토

```bash
python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/srvd2insomnia.py \
  --srvd <srvd 파일> --src-dir <CDS/BDEF 폴더> \
  --collection-name "<컬렉션 이름>" --binding <바인딩> --odata v4 --binding-type ui \
  --base-url https://<host>:<port> --sap-client 100 \
  --dump-spec <scratchpad>/spec.json
```

stderr 경고(키를 모름, BDEF 없음 등)를 읽고 `spec.json`을 직접 고친다. 파서는 휴리스틱 방식이라 아래 항목을 꼭 확인한다:

- `keys[].type`: `guid` | `string` | `number`. 이 값으로 키 리터럴이 정해진다. V4는 guid/number에 따옴표를 붙이지 않고 string에는 `'..'`를 붙인다. V2는 `guid'..'`를 쓴다. 이름이 `UUID`로 끝나면 guid로 추정한다.
- `root`, `draft`, `create`/`update`/`delete`, `actions`, `createByAssociation`, `associations`
- CDS 소스가 없는 값 도움말용 엔티티는 `keys`가 비어 있으면 List만 생성된다.

## 3. Insomnia export 렌더링

```bash
python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/srvd2insomnia.py \
  --spec <scratchpad>/spec.json -o <scratchpad>/<컬렉션>.insomnia.json
```

`--collection-name`, `--binding`, `--odata`, `--binding-type`, `--service-version`, `--base-url`, `--sap-client`를 주면 spec 값보다 우선한다.

- V4 액션 경로: `<Entity>(<keys>)/com.sap.gateway.srvd.<srvd>.v<버전>.<action>` (static 액션은 컬렉션에 바인딩)
- draft가 켜진 엔티티는 Update와 자식 Delete가 `IsActiveEntity=false` draft 인스턴스를 대상으로 한다.
- V2 액션/draft는 function import(`/<action>?<keys>`, `/<Entity>Edit` 등)로 생성한다. 이름에 접두사가 붙는 경우가 있으니 `$metadata`로 확인하라고 알린다.

## 4. Insomnia 종료 → MCP 연동 → 재시작

mcp-insomnia는 Insomnia NeDB 파일에 직접 쓴다. 실행 중인 앱은 메모리의 데이터로 이 파일을 덮어쓰므로 **반드시 앱을 종료한 뒤 연동**한다.

`mcp__insomnia__*` 도구가 없으면 ToolSearch로 `insomnia`를 검색한다. 그래도 없으면 `/mcp`에서 서버 승인 여부를 확인하라고 안내하고, 5단계의 파일 import로 넘어간다.

1. `import_from_insomnia_export` { filePath: 생성한 JSON의 **절대 경로** }: MCP 저장소(`~/.mcp-insomnia`)에 등록
2. 컬렉션 ID는 생성한 JSON의 `resources[0]._id`(`wrk_...`)다. `list_collections`로 확인할 수도 있다.
3. `list_insomnia_projects`로 프로젝트 ID를 확인한다. `projectId`는 **항상 명시**한다. 생략하면 존재하지 않는 `proj_default`에 들어갈 수 있다. 여러 개면 사용자에게 고르게 한다.
4. `sync_to_insomnia` { collectionId, projectId, dryRun: true }로 생성/수정/삭제될 문서를 보여준다.
5. 사용자가 확인하면 저장하지 않은 작업이 닫힌다는 점을 알리고 앱을 종료한다:
   ```bash
   python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/insomnia_app.py stop
   ```
   먼저 정상 종료를 시도하고, 15초 안에 끝나지 않으면 강제로 종료한다.
   - Windows: `taskkill /IM Insomnia.exe /T`, 이후 `/F`
   - macOS: `quit app "Insomnia"`, 이후 `pkill -9`
   - Linux: `pkill -x insomnia`, 이후 `-9`

   프로세스 이름이 정확히 일치할 때만 종료하므로 mcp-insomnia(node) 프로세스는 건드리지 않는다. 종료 코드가 1이면(여전히 실행 중) 연동하지 말고 사용자에게 직접 종료해 달라고 한다.
6. `sync_to_insomnia` { collectionId, projectId, backup: true }: 덮어쓸 문서의 백업은 `~/.mcp-insomnia/backups`에 남는다.
7. 앱을 다시 실행한다:
   ```bash
   python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/insomnia_app.py start
   ```
   실행 파일을 찾지 못하면 `--exe <경로>`를 준다. Windows 기본 경로는 `%LOCALAPPDATA%\insomnia\Insomnia.exe`다.

"Insomnia data directory not found"가 나오면 Insomnia가 없는 환경(클라우드 세션 등)이다. `INSOMNIA_DATA_DIR`로 경로를 지정하거나 5단계로 넘어간다.

시스템에 접속할 수 있고 사용자가 원하면 `execute_request`로 `Fetch CSRF token`과 `$metadata`를 실행해 엔티티 셋, 액션 이름, 키 타입이 실제와 맞는지 확인한다. 다르면 spec을 고쳐 3단계부터 다시 한다. MCP 실행기는 `csrf_token`의 response 태그를 해석하지 못할 수 있으니 Post 요청은 Insomnia 앱에서 실행하라고 안내한다.

## 5. 마무리 안내

- 생성 파일 경로, 요청 개수(Setting/Get/Post별), 경고를 알려준다.
- Insomnia에서 채워야 할 값: `base_url`, `sap_client`, `username`, `password`, `<Entity>_<Key>`, 요청 본문의 `<Field>` 자리표시자
- 사용 순서: `Setting/Fetch CSRF token` 실행 → `Get` / `Post` 요청 실행
- MCP를 쓰지 못한 경우: Insomnia → **Import** → 생성한 JSON 파일 선택
- 비밀번호는 파일에 쓰지 않는다.

## 참고

- 예제 소스: `examples/` (draft가 켜진 Travel/Booking, V4 UI 서비스)
  ```bash
  python3 -I .claude/skills/rap-srvd-to-insomnia/scripts/srvd2insomnia.py \
    --srvd .claude/skills/rap-srvd-to-insomnia/examples/zui_travel.srvd.srvdsrv \
    --src-dir .claude/skills/rap-srvd-to-insomnia/examples \
    --collection-name "Travel" -o <scratchpad>/travel.json
  ```
- 매칭 규칙: SRVD의 `expose <CDS> as <Alias>`에서 CDS 이름으로 CDS 소스와 BDEF(`define behavior for <CDS>`)를 찾는다. 같은 엔티티에 프로젝션 BDEF와 인터페이스 BDEF가 둘 다 있으면 프로젝션 BDEF를 우선한다. 액션 파라미터 구조는 인터페이스 BDEF에서 가져온다. `internal` 동작과 draft 액션 선언은 일반 액션 목록에서 뺀다.
