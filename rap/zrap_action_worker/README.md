# RAP Action Worker 골격 (factory + interface + worker)

Root BO 하나에 action 을 모두 정의하고, **action 하나당 worker 클래스 하나**를 factory 가 만들어 호출한다.
Web API 는 projection BDEF 의 `use action` 으로 필요한 action 만 노출한다.

> 이 저장소에는 ABAP 시스템이 없어 **컴파일/실행은 하지 않았다.** ADT 로 가져간 뒤 구문 검사와 ABAP Unit 실행이 필요하다.

## 구조

```
handler (lhc_travel)                 EML 담당: 읽기 → worker 호출 → 저장
   │  zcl_trv_action_factory=>create( action )
   ▼
zcl_trv_action_factory               action(ENUM) → worker 인스턴스 (SWITCH)
   │
   ▼
zif_trv_action                       execute( travel, param ) → changes
   ├── zcl_trv_action_accept         상태 O → A
   ├── zcl_trv_action_reject         상태 O → X
   └── zcl_trv_action_discount       TotalPrice 할인 (%param 사용)
```

역할은 둘로만 나뉜다.

- **handler**: `IN LOCAL MODE` EML 로 읽고 저장한다. 업무 로직은 없다.
- **worker**: travel 한 건을 받아 **바꿀 값**(`%control` 포함)을 돌려준다. 업무 오류는 `zcx_trv_action` 으로 던진다. EML 이 없으므로 `NEW` 해서 바로 단위 테스트할 수 있다.

`IN LOCAL MODE` 는 behavior pool 안에서만 쓸 수 있어서 EML 을 handler 에 두었다.

## 호출 흐름

```abap
METHOD acceptTravel.
  LOOP AT keys INTO FINAL(key).
    run_action( EXPORTING action   = zif_trv_action=>accept_travel
                          key      = CORRESPONDING #( key )
                CHANGING  failed   = failed
                          reported = reported ).
  ENDLOOP.

  result = VALUE #( FOR travel IN read_travels( CORRESPONDING #( keys ) )
                    ( %tky = travel-%tky  %param = travel ) ).
ENDMETHOD.
```

`run_action` 은 모든 action 이 공유한다: 한 건 읽기 → `factory=>create( action )->execute( ... )` → `MODIFY`.
예외가 나면 `failed` 와 `reported`(`new_message_with_text`) 에 넣는다.

## 새 action 추가

1. `zi_travel.bdef.asbdef` 에 action 정의
2. `zif_trv_action` 의 `ty_action` ENUM 에 값 추가
3. `zif_trv_action` 을 구현한 worker 클래스 작성
4. `zcl_trv_action_factory=>create` 에 `WHEN` 한 줄
5. `lhc_travel` 에 action 메서드 추가 (위 모양 그대로, 파라미터가 있으면 `param = key-%param`)
6. 노출할 Web API 의 projection BDEF 에 `use action`

## Web API 별 노출

| Web API (SRVD) | Projection | 노출 |
|---|---|---|
| `ZAPI_TRAVEL_APPROVAL` | `ZC_Travel_Api_Approval` | `acceptTravel`, `rejectTravel` |
| `ZAPI_TRAVEL_PRICING` | `ZC_Travel_Api_Pricing` | `update`, `deductDiscount` |

Service Binding(OData V4 - Web API)은 포함하지 않았다.

## 파일

| 파일 | 역할 |
|---|---|
| `src/zif_trv_action.intf.abap` | worker 인터페이스, action ENUM, 상태 상수 |
| `src/zcl_trv_action_factory.clas.abap` | factory |
| `src/zcl_trv_action_accept/reject/discount.clas.abap` | worker |
| `src/zcx_trv_action.clas.abap`, `src/ztrv_action.msag.xml` | 업무 오류 예외, 메시지 클래스 |
| `src/zbp_i_travel.clas.locals_imp.abap` | handler |
| `src/zi_travel.*`, `src/za_discount.ddls.asddls` | Root BO, action 파라미터 |
| `src/zc_travel_api_*`, `src/zapi_travel_*.srvd.srvdsrv` | Web API projection 2종 |
| `src/*.testclasses.abap` | worker, factory 단위 테스트 |

## 참고

- `FINAL( )` 인라인 선언을 쓴다. ABAP 7.57(S/4HANA 2022) 이상 또는 ABAP Cloud 가 필요하다. 그 아래 릴리스면 `DATA( )` 로 바꾼다.
- 테이블 `ztravel` 은 포함하지 않았다. 필드: `travel_uuid`(key), `travel_id`, `agency_id`, `customer_id`, `begin_date`, `end_date`, `total_price`, `currency_code`, `overall_status`, `last_changed_at`, `local_last_changed_at`.
- `get_instance_authorizations` 는 전부 허용하는 스텁이다.
- 파라미터는 `param TYPE any` 로 받는다. worker 가 자기 파라미터 타입(예: `za_discount`)에 대입해서 쓴다.
