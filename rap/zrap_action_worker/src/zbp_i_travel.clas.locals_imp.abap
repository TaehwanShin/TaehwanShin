"! BO 내부 접근 게이트웨이 구현.
"! IN LOCAL MODE EML 은 behavior pool 안에서만 허용되므로 로컬 클래스로 두고 글로벌 worker 에 주입한다.
CLASS lcl_bo_gateway DEFINITION FINAL CREATE PUBLIC.
  PUBLIC SECTION.
    INTERFACES zif_trv_bo_gateway.
ENDCLASS.

CLASS lcl_bo_gateway IMPLEMENTATION.

  METHOD zif_trv_bo_gateway~read_travels.
    READ ENTITIES OF zi_travel IN LOCAL MODE
      ENTITY Travel
        ALL FIELDS WITH CORRESPONDING #( it_keys )
      RESULT rt_travels.
  ENDMETHOD.

  METHOD zif_trv_bo_gateway~update_travels.
    MODIFY ENTITIES OF zi_travel IN LOCAL MODE
      ENTITY Travel
        UPDATE FROM it_updates
      FAILED   DATA(ls_failed)
      REPORTED DATA(ls_reported).

    APPEND LINES OF ls_failed-travel   TO cs_failed-travel.
    APPEND LINES OF ls_reported-travel TO cs_reported-travel.
  ENDMETHOD.

ENDCLASS.


"! handler 의 action 메서드 → factory → worker 로 넘기는 단일 진입점.
"! action 메서드는 action 이름 상수만 넘기면 된다.
CLASS lcl_action_dispatcher DEFINITION FINAL CREATE PRIVATE.
  PUBLIC SECTION.
    CLASS-METHODS dispatch
      IMPORTING iv_action   TYPE string
                it_keys     TYPE ANY TABLE
      CHANGING  ct_result   TYPE ANY TABLE
                cs_failed   TYPE zif_trv_bo_gateway=>ts_failed
                cs_reported TYPE zif_trv_bo_gateway=>ts_reported.
ENDCLASS.

CLASS lcl_action_dispatcher IMPLEMENTATION.

  METHOD dispatch.
    DATA lt_keys TYPE zif_trv_bo_gateway=>tt_travel_key.

    TRY.
        zcl_trv_action_factory=>get_instance( )->create( iv_action )->execute(
          EXPORTING it_keys     = it_keys
                    io_gateway  = NEW lcl_bo_gateway( )
          CHANGING  ct_result   = ct_result
                    cs_failed   = cs_failed
                    cs_reported = cs_reported ).

      CATCH zcx_trv_action INTO DATA(lx_config).
        " worker 미등록/생성 실패는 구성 오류. 요청된 모든 인스턴스를 실패 처리한다.
        MOVE-CORRESPONDING it_keys TO lt_keys.
        LOOP AT lt_keys INTO DATA(ls_key).
          APPEND VALUE #( %tky        = ls_key-%tky
                          %fail-cause = if_abap_behv=>cause-unspecific ) TO cs_failed-travel.
          APPEND VALUE #( %tky = ls_key-%tky
                          %msg = lx_config ) TO cs_reported-travel.
        ENDLOOP.
    ENDTRY.
  ENDMETHOD.

ENDCLASS.


CLASS lhc_travel DEFINITION INHERITING FROM cl_abap_behavior_handler.
  PRIVATE SECTION.
    METHODS get_instance_features FOR INSTANCE FEATURES
      IMPORTING keys REQUEST requested_features FOR Travel RESULT result.

    METHODS get_instance_authorizations FOR INSTANCE AUTHORIZATION
      IMPORTING keys REQUEST requested_authorizations FOR Travel RESULT result.

    METHODS acceptTravel FOR MODIFY
      IMPORTING keys FOR ACTION Travel~acceptTravel RESULT result.

    METHODS rejectTravel FOR MODIFY
      IMPORTING keys FOR ACTION Travel~rejectTravel RESULT result.

    METHODS reopenTravel FOR MODIFY
      IMPORTING keys FOR ACTION Travel~reopenTravel RESULT result.

    METHODS deductDiscount FOR MODIFY
      IMPORTING keys FOR ACTION Travel~deductDiscount RESULT result.

    METHODS feature_for_transition
      IMPORTING iv_from           TYPE zi_travel-OverallStatus
                iv_to             TYPE zi_travel-OverallStatus
      RETURNING VALUE(rv_feature) TYPE if_abap_behv=>t_xflag.
ENDCLASS.

CLASS lhc_travel IMPLEMENTATION.

  METHOD get_instance_features.
    READ ENTITIES OF zi_travel IN LOCAL MODE
      ENTITY Travel
        FIELDS ( OverallStatus ) WITH CORRESPONDING #( keys )
      RESULT DATA(lt_travels)
      FAILED failed.

    " worker 의 사전조건과 같은 규칙(zcl_trv_status_rules)을 쓴다.
    result = VALUE #( FOR ls_travel IN lt_travels
                      ( %tky                 = ls_travel-%tky
                        %action-acceptTravel = feature_for_transition( iv_from = ls_travel-OverallStatus
                                                                       iv_to   = zcl_trv_status_rules=>c_status-accepted )
                        %action-rejectTravel = feature_for_transition( iv_from = ls_travel-OverallStatus
                                                                       iv_to   = zcl_trv_status_rules=>c_status-rejected )
                        %action-reopenTravel = feature_for_transition( iv_from = ls_travel-OverallStatus
                                                                       iv_to   = zcl_trv_status_rules=>c_status-open ) ) ).
  ENDMETHOD.

  METHOD feature_for_transition.
    rv_feature = COND #( WHEN zcl_trv_status_rules=>is_transition_allowed( iv_from = iv_from
                                                                           iv_to   = iv_to ) = abap_true
                         THEN if_abap_behv=>fc-o-enabled
                         ELSE if_abap_behv=>fc-o-disabled ).
  ENDMETHOD.

  METHOD get_instance_authorizations.
    " TODO: 실제 권한 객체 검사로 교체. 골격에서는 전부 허용.
    result = VALUE #( FOR ls_key IN keys
                      ( %tky                   = ls_key-%tky
                        %update                = if_abap_behv=>auth-allowed
                        %delete                = if_abap_behv=>auth-allowed
                        %action-acceptTravel   = if_abap_behv=>auth-allowed
                        %action-rejectTravel   = if_abap_behv=>auth-allowed
                        %action-reopenTravel   = if_abap_behv=>auth-allowed
                        %action-deductDiscount = if_abap_behv=>auth-allowed ) ).
  ENDMETHOD.

  " ---- action: 모두 같은 모양. 새 action 은 아래 3줄짜리 메서드 하나와 factory 등록 한 줄이면 된다. ----

  METHOD acceptTravel.
    lcl_action_dispatcher=>dispatch( EXPORTING iv_action   = zif_trv_action=>c_action-accept_travel
                                               it_keys     = keys
                                     CHANGING  ct_result   = result
                                               cs_failed   = failed
                                               cs_reported = reported ).
  ENDMETHOD.

  METHOD rejectTravel.
    lcl_action_dispatcher=>dispatch( EXPORTING iv_action   = zif_trv_action=>c_action-reject_travel
                                               it_keys     = keys
                                     CHANGING  ct_result   = result
                                               cs_failed   = failed
                                               cs_reported = reported ).
  ENDMETHOD.

  METHOD reopenTravel.
    lcl_action_dispatcher=>dispatch( EXPORTING iv_action   = zif_trv_action=>c_action-reopen_travel
                                               it_keys     = keys
                                     CHANGING  ct_result   = result
                                               cs_failed   = failed
                                               cs_reported = reported ).
  ENDMETHOD.

  METHOD deductDiscount.
    lcl_action_dispatcher=>dispatch( EXPORTING iv_action   = zif_trv_action=>c_action-deduct_discount
                                               it_keys     = keys
                                     CHANGING  ct_result   = result
                                               cs_failed   = failed
                                               cs_reported = reported ).
  ENDMETHOD.

ENDCLASS.
