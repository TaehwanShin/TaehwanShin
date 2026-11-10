"! <p class="shorttext synchronized">Travel BO 내부 접근 게이트웨이</p>
"! worker 가 BO 를 읽고/변경할 때 쓰는 유일한 통로.
"! IN LOCAL MODE EML 은 behavior pool 안에서만 허용되므로 실제 구현(lcl_bo_gateway)은
"! zbp_i_travel 의 로컬 클래스에 있고, 단위 테스트에서는 test double 로 대체한다.
INTERFACE zif_trv_bo_gateway
  PUBLIC.

  TYPES tt_travel_key    TYPE TABLE FOR READ IMPORT zi_travel\\Travel.
  TYPES tt_travel        TYPE TABLE FOR READ RESULT zi_travel\\Travel.
  TYPES tt_travel_update TYPE TABLE FOR UPDATE      zi_travel\\Travel.
  TYPES ts_failed        TYPE RESPONSE FOR FAILED   EARLY zi_travel.
  TYPES ts_reported      TYPE RESPONSE FOR REPORTED EARLY zi_travel.

  "! 키에 해당하는 Travel 인스턴스를 전체 필드로 읽는다. 존재하지 않는 키는 결과에서 빠진다.
  METHODS read_travels
    IMPORTING it_keys           TYPE tt_travel_key
    RETURNING VALUE(rt_travels) TYPE tt_travel.

  "! %control 이 켜진 필드만 변경한다. BO 가 돌려준 failed/reported 를 누적한다.
  METHODS update_travels
    IMPORTING it_updates  TYPE tt_travel_update
    CHANGING  cs_failed   TYPE ts_failed
              cs_reported TYPE ts_reported.

ENDINTERFACE.
