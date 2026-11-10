# RAP Action Worker 골격 (Factory + Worker per Action)

Root BO 하나에 action 을 모두 정의하고, **action 하나당 worker 클래스 하나**를 factory 가 생성해서 호출하는 구조다.
Web API 는 projection BDEF 에서 `use action` 으로 필요한 action 만 노출한다.

> 이 저장소에는 ABAP 시스템이 없어 **컴파일/실행은 하지 않았다.** ADT 로 가져간 뒤 구문 검사와 ABAP Unit 실행이 필요하다. 아래 "검증 필요" 절 참고.

## 구조

```
Web API (Service Binding, OData V4 Web API)
  ZAPI_TRAVEL_APPROVAL ──► ZC_Travel_Api_Approval  (use action accept/reject/reopen)
  ZAPI_TRAVEL_PRICING  ──► ZC_Travel_Api_Pricing   (use update, use action deductDiscount)
                                   │ projection on
                                   ▼
                         ZI_Travel (Root BO, 모든 action 정의)
                                   │ managed implementation in class
                                   ▼
┌─ zbp_i_travel (behavior pool) ───────────────────────────────────────────────┐
│  lhc_travel            action 메서드 = 3줄. lcl_action_dispatcher 호출만 한다  │
│  lcl_action_dispatcher factory → worker → execute. 구성 오류는 전체 실패 처리   │
│  lcl_bo_gateway        IN LOCAL MODE READ/MODIFY. zif_trv_bo_gateway 구현       │
└──────────────┬────────────────────────────────────────────┬──────────────────┘
               │ create( action )                           │ 주입 (io_gateway)
               ▼                                            ▼
  zcl_trv_action_factory                         zif_trv_bo_gateway
    레지스트리: action 이름 → 클래스 이름                   │
    호출마다 새 worker 생성, 테스트용 inject/reset          │
               │                                            │
               ▼                                            │
  zif_trv_action ◄── zcl_trv_action_base (ABSTRACT, 템플릿 메서드) ◄── 사용
                        │  execute: 키 변환 → 읽기 → 사전조건 → process → UPDATE → result
                        │
                        ├── zcl_trv_action_status_base (ABSTRACT) ── zcl_trv_status_rules 참조
                        │     ├── zcl_trv_action_accept   (target = A)
                        │     ├── zcl_trv_action_reject   (target = X)
                        │     └── zcl_trv_action_reopen   (target = O)
                        └── zcl_trv_action_deduct_disc    (파라미터 action, %param 사용)

  zcx_trv_action        예외 겸 RAP 메시지 (if_abap_behv_message). 메시지 클래스 ZTRV_ACTION
  zcl_trv_status_rules  상태 전이 규칙 단일 소스. handler 의 feature control 과 worker 가 함께 사용
```

## 호출 흐름 (acceptTravel 예)

1. OData 요청 → `ZC_Travel_Api_Approval` → `ZI_Travel` 의 `acceptTravel` → `lhc_travel->acceptTravel`.
2. handler 는 `lcl_action_dispatcher=>dispatch( iv_action = 'ACCEPTTRAVEL' ... )` 만 호출한다.
3. dispatcher 가 `zcl_trv_action_factory=>get_instance( )->create( 'ACCEPTTRAVEL' )` 로 `zcl_trv_action_accept` 를 만들고, `lcl_bo_gateway` 인스턴스를 넘겨 `execute` 한다.
4. `zcl_trv_action_base->execute` (템플릿 메서드)
   1. `MOVE-CORRESPONDING keys` 로 BO 공통 읽기 키를 만들고 `on_prepare` 훅 호출
   2. 게이트웨이로 인스턴스 읽기. 없는 키는 `%fail-cause = not_found`
   3. 인스턴스마다 `check_precondition` → 통과하면 `process`. `zcx_trv_action` 은 failed + reported(%msg) 로 변환
   4. 게이트웨이로 `UPDATE` (IN LOCAL MODE 이므로 readonly 필드도 변경 가능)
   5. 실패하지 않은 인스턴스를 다시 읽어 `result` (`$self`) 를 채움. `on_after_update` 훅 호출
5. worker 미등록 등 구성 오류는 dispatcher 가 잡아 요청된 모든 키를 실패 처리한다.

## 왜 이렇게 나눴나

| 결정 | 이유 |
|---|---|
| worker 는 **글로벌 클래스** | ABAP Unit 으로 CDS/DB 없이 단독 테스트. 다른 BO 나 배치에서 재사용 가능 |
| BO 접근은 **게이트웨이 인터페이스**로 주입 | `IN LOCAL MODE` EML 은 behavior pool 안에서만 허용된다. 구현은 로컬 클래스(`lcl_bo_gateway`), worker 는 인터페이스만 안다. 테스트는 메모리 double 로 대체 |
| `execute` 의 키/결과는 `ANY TABLE` | `TABLE FOR ACTION IMPORT/RESULT` 는 action 마다 다른 타입. `%tky` 는 공통이므로 base 가 `MOVE-CORRESPONDING` 으로 변환하고, 결과는 `%TKY`/`%PARAM` 컴포넌트에 동적으로 채운다 |
| factory 는 **호출마다 새 인스턴스** | 파라미터 action worker 가 typed keys 를 멤버에 보관한다. 재사용하면 호출 간 상태가 샌다 |
| 상태 전이 규칙은 `zcl_trv_status_rules` 한 곳 | feature control(버튼 활성화)과 worker 사전조건(실행 거부)이 같은 표를 본다. 두 곳이 어긋나는 흔한 버그를 막는다 |
| 상태 action 은 `zcl_trv_action_status_base` 로 묶음 | accept/reject/reopen 은 목표 상태만 다르다. 각 worker 는 메서드 하나 |

## 새 action 추가 절차

예: `cancelTravel` 추가.

1. **BDEF** `zi_travel.bdef.asbdef` 에 `action ( features : instance ) cancelTravel result [1] $self;`
2. **상수** `zif_trv_action=>c_action` 에 `cancel_travel TYPE string VALUE 'CANCELTRAVEL'`
3. **worker** `zcl_trv_action_cancel` 작성
   - 상태 전이면 `zcl_trv_action_status_base` 상속 + `get_target_status` 만 구현하고, `zcl_trv_status_rules` 전이 표에 행 추가
   - 그 외면 `zcl_trv_action_base` 상속 + `process` 구현 (필요 시 `check_precondition`, `on_prepare`, `on_after_update`)
4. **factory** `register_defaults` 에 `->register( iv_action = ... iv_class = 'ZCL_TRV_ACTION_CANCEL' )` 한 줄
5. **handler** `lhc_travel` 에 `METHODS cancelTravel FOR MODIFY ...` 선언 + dispatch 3줄 구현
6. **노출할 Web API 의 projection BDEF** 에만 `use action cancelTravel;`
7. 테스트: `zcl_trv_action_accept.clas.testclasses.abap` 의 `ltd_gateway` 를 복사해 worker 단위 테스트 작성

## Web API 별 노출 action

| Web API (SRVD) | Projection | 노출 |
|---|---|---|
| `ZAPI_TRAVEL_APPROVAL` | `ZC_Travel_Api_Approval` | `acceptTravel`, `rejectTravel`, `reopenTravel` (CUD 없음) |
| `ZAPI_TRAVEL_PRICING` | `ZC_Travel_Api_Pricing` | `update`, `deductDiscount` |

Service Binding 은 각 SRVD 에 대해 **OData V4 - Web API** 로 만든다 (이 파일 묶음에는 포함하지 않음).
새 API 가 필요하면 projection CDS + projection BDEF + SRVD 세트를 하나 더 만들면 된다. Root BO 와 worker 는 건드리지 않는다.

## 파일

| 파일 | 역할 |
|---|---|
| `src/zi_travel.ddls.asddls`, `src/zi_travel.bdef.asbdef` | Root BO (managed, non-draft) |
| `src/za_discount.ddls.asddls` | `deductDiscount` 파라미터 |
| `src/zbp_i_travel.clas.abap`, `src/zbp_i_travel.clas.locals_imp.abap` | behavior pool: handler, dispatcher, gateway |
| `src/zif_trv_bo_gateway.intf.abap` | BO 접근 게이트웨이 계약 |
| `src/zif_trv_action.intf.abap` | worker 계약 + action 이름 상수 |
| `src/zcl_trv_action_factory.clas.abap` (+ `.testclasses`) | 레지스트리 팩토리 |
| `src/zcl_trv_action_base.clas.abap` | 템플릿 메서드 베이스 |
| `src/zcl_trv_action_status_base.clas.abap` | 상태 전이 action 베이스 |
| `src/zcl_trv_action_accept/reject/reopen.clas.abap` | 상태 전이 worker |
| `src/zcl_trv_action_deduct_disc.clas.abap` | 파라미터 action worker |
| `src/zcl_trv_status_rules.clas.abap` | 상태 상수 + 전이 표 |
| `src/zcx_trv_action.clas.abap`, `src/ztrv_action.msag.xml` | 예외/메시지 |
| `src/zc_travel_api_*.ddls/bdef`, `src/zapi_travel_*.srvd.srvdsrv` | Web API projection 2종 |

## 검증 필요 (ADT 에서 확인할 것)

- **테이블 `ztravel`** 은 포함하지 않았다. 필드: `travel_uuid`(sysuuid_x16, key), `travel_id`, `agency_id`, `customer_id`, `begin_date`, `end_date`, `total_price`, `currency_code`, `overall_status`(char1), `last_changed_at`, `local_last_changed_at`.
- `zcl_trv_action_base->fill_result` 의 `ASSIGN COMPONENT '%TKY' / '%PARAM'` 과 `MOVE-CORRESPONDING` 을 통한 제네릭 → 파생 타입 변환은 런타임 타입 호환에 의존한다. ABAP Unit 의 `open_travel_gets_accepted` 가 이 경로를 그대로 지나가므로 첫 실행에서 바로 드러난다.
- `if_abap_behv=>t_xflag` 를 feature control 값 타입으로 썼다. 릴리스에 따라 타입명이 다르면 `feature_for_transition` 의 RETURNING 타입만 바꾸면 된다.
- 메시지 클래스 `ZTRV_ACTION` 은 abapGit 형식 XML 로 넣었다. abapGit 을 쓰지 않으면 README 의 텍스트대로 수동 생성한다.
- `get_instance_authorizations` 는 전부 허용하는 스텁이다.
