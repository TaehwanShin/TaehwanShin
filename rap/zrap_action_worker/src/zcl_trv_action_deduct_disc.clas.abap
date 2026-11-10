"! <p class="shorttext synchronized">Worker: deductDiscount (파라미터 action 예시)</p>
"! on_prepare 에서 action 전용 typed keys 를 보관해 두고, process 에서 %param 을 꺼내 쓴다.
CLASS zcl_trv_action_deduct_disc DEFINITION
  PUBLIC
  INHERITING FROM zcl_trv_action_base
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
  PROTECTED SECTION.
    METHODS on_prepare         REDEFINITION.
    METHODS check_precondition REDEFINITION.
    METHODS process            REDEFINITION.
  PRIVATE SECTION.
    TYPES tt_keys TYPE TABLE FOR ACTION IMPORT zi_travel~deductDiscount.

    CONSTANTS c_min_percent TYPE i VALUE 1.
    CONSTANTS c_max_percent TYPE i VALUE 100.

    DATA mt_keys TYPE tt_keys.
ENDCLASS.


CLASS zcl_trv_action_deduct_disc IMPLEMENTATION.

  METHOD on_prepare.
    " 제네릭 keys → 이 action 의 typed keys (%param 포함)
    MOVE-CORRESPONDING it_keys TO mt_keys.
  ENDMETHOD.

  METHOD check_precondition.
    IF is_travel-OverallStatus = zcl_trv_status_rules=>c_status-rejected.
      ro_message = NEW zcx_trv_action( textid   = zcx_trv_action=>discount_not_allowed
                                        mv_attr1 = |{ is_travel-TravelID }|
                                        mv_attr2 = |{ is_travel-OverallStatus }| ).
    ENDIF.
  ENDMETHOD.

  METHOD process.
    DATA(lv_percent) = mt_keys[ %tky = is_travel-%tky ]-%param-discount_percent.

    IF lv_percent < c_min_percent OR lv_percent > c_max_percent.
      RAISE EXCEPTION NEW zcx_trv_action( textid   = zcx_trv_action=>invalid_discount
                                           mv_attr1 = |{ is_travel-TravelID }|
                                           mv_attr2 = |{ lv_percent }| ).
    ENDIF.

    cs_update-TotalPrice          = is_travel-TotalPrice - ( is_travel-TotalPrice * lv_percent / 100 ).
    cs_update-%control-TotalPrice = if_abap_behv=>mk-on.
  ENDMETHOD.

ENDCLASS.
