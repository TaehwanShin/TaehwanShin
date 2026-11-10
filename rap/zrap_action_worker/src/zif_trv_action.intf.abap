"! <p class="shorttext synchronized">Travel action worker 계약</p>
"! action 하나 = worker 클래스 하나. 인스턴스는 zcl_trv_action_factory 가 만든다.
"! 키/결과 타입은 action 마다 다르므로(TABLE FOR ACTION IMPORT/RESULT) 제네릭으로 받고,
"! 구현(zcl_trv_action_base)에서 BO 공통 타입으로 변환한다.
INTERFACE zif_trv_action
  PUBLIC.

  "! handler 와 factory 가 공유하는 action 식별자. BDEF 의 action 이름(대문자)과 같다.
  CONSTANTS:
    BEGIN OF c_action,
      accept_travel   TYPE string VALUE 'ACCEPTTRAVEL',
      reject_travel   TYPE string VALUE 'REJECTTRAVEL',
      reopen_travel   TYPE string VALUE 'REOPENTRAVEL',
      deduct_discount TYPE string VALUE 'DEDUCTDISCOUNT',
    END OF c_action.

  "! @parameter it_keys     | handler 의 keys (TABLE FOR ACTION IMPORT zi_travel~&lt;action&gt;)
  "! @parameter io_gateway  | BO 접근 게이트웨이 (behavior pool 이 주입)
  "! @parameter ct_result   | handler 의 result (TABLE FOR ACTION RESULT, $self)
  "! @parameter cs_failed   | handler 의 failed
  "! @parameter cs_reported | handler 의 reported
  METHODS execute
    IMPORTING it_keys     TYPE ANY TABLE
              io_gateway  TYPE REF TO zif_trv_bo_gateway
    CHANGING  ct_result   TYPE ANY TABLE
              cs_failed   TYPE zif_trv_bo_gateway=>ts_failed
              cs_reported TYPE zif_trv_bo_gateway=>ts_reported.

ENDINTERFACE.
