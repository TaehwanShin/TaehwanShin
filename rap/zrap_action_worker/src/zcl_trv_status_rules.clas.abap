"! <p class="shorttext synchronized">Travel 상태 전이 규칙 (단일 소스)</p>
"! feature control(handler)과 worker 의 사전조건이 모두 이 클래스를 참조한다.
"! 상태나 전이를 추가할 때는 여기만 고친다.
CLASS zcl_trv_status_rules DEFINITION
  PUBLIC
  FINAL
  CREATE PRIVATE.

  PUBLIC SECTION.
    CONSTANTS:
      BEGIN OF c_status,
        open     TYPE zi_travel-OverallStatus VALUE 'O',
        accepted TYPE zi_travel-OverallStatus VALUE 'A',
        rejected TYPE zi_travel-OverallStatus VALUE 'X',
      END OF c_status.

    "! iv_from → iv_to 전이가 허용되면 abap_true
    CLASS-METHODS is_transition_allowed
      IMPORTING iv_from           TYPE zi_travel-OverallStatus
                iv_to             TYPE zi_travel-OverallStatus
      RETURNING VALUE(rv_allowed) TYPE abap_bool.

    CLASS-METHODS class_constructor.

  PROTECTED SECTION.
  PRIVATE SECTION.
    TYPES:
      BEGIN OF ts_transition,
        status_from TYPE zi_travel-OverallStatus,
        status_to   TYPE zi_travel-OverallStatus,
      END OF ts_transition.
    TYPES tt_transition TYPE HASHED TABLE OF ts_transition WITH UNIQUE KEY status_from status_to.

    CLASS-DATA gt_transitions TYPE tt_transition.
ENDCLASS.


CLASS zcl_trv_status_rules IMPLEMENTATION.

  METHOD class_constructor.
    gt_transitions = VALUE #(
      ( status_from = c_status-open     status_to = c_status-accepted )   " acceptTravel
      ( status_from = c_status-open     status_to = c_status-rejected )   " rejectTravel
      ( status_from = c_status-accepted status_to = c_status-open     )   " reopenTravel
      ( status_from = c_status-rejected status_to = c_status-open     ) ). " reopenTravel
  ENDMETHOD.

  METHOD is_transition_allowed.
    rv_allowed = xsdbool( line_exists( gt_transitions[ status_from = iv_from
                                                       status_to   = iv_to ] ) ).
  ENDMETHOD.

ENDCLASS.
