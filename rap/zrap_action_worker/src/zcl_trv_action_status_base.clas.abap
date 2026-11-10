"! <p class="shorttext synchronized">상태 전이 action 공통 베이스</p>
"! accept/reject/reopen 은 "목표 상태" 만 다르다. 전이 허용 여부는 zcl_trv_status_rules 에 묻는다.
CLASS zcl_trv_action_status_base DEFINITION
  PUBLIC
  ABSTRACT
  INHERITING FROM zcl_trv_action_base
  CREATE PUBLIC.

  PUBLIC SECTION.
  PROTECTED SECTION.
    "! 이 action 이 도달시키는 상태
    METHODS get_target_status ABSTRACT
      RETURNING VALUE(rv_status) TYPE zi_travel-OverallStatus.

    METHODS check_precondition REDEFINITION.
    METHODS process            REDEFINITION.
  PRIVATE SECTION.
ENDCLASS.


CLASS zcl_trv_action_status_base IMPLEMENTATION.

  METHOD check_precondition.
    DATA(lv_target) = get_target_status( ).

    IF zcl_trv_status_rules=>is_transition_allowed( iv_from = is_travel-OverallStatus
                                                     iv_to   = lv_target ) = abap_false.
      ro_message = NEW zcx_trv_action( textid   = zcx_trv_action=>status_not_allowed
                                        mv_attr1 = |{ is_travel-TravelID }|
                                        mv_attr2 = |{ is_travel-OverallStatus }|
                                        mv_attr3 = |{ lv_target }| ).
    ENDIF.
  ENDMETHOD.

  METHOD process.
    cs_update-OverallStatus          = get_target_status( ).
    cs_update-%control-OverallStatus = if_abap_behv=>mk-on.
  ENDMETHOD.

ENDCLASS.
