CLASS lhc_travel DEFINITION INHERITING FROM cl_abap_behavior_handler.
  PRIVATE SECTION.
    TYPES ty_key      TYPE STRUCTURE FOR READ IMPORT zi_travel\\Travel.
    TYPES tt_keys     TYPE TABLE FOR READ IMPORT     zi_travel\\Travel.
    TYPES tt_travels  TYPE TABLE FOR READ RESULT     zi_travel\\Travel.
    TYPES ty_failed   TYPE RESPONSE FOR FAILED   EARLY zi_travel.
    TYPES ty_reported TYPE RESPONSE FOR REPORTED EARLY zi_travel.

    METHODS get_instance_authorizations FOR INSTANCE AUTHORIZATION
      IMPORTING keys REQUEST requested_authorizations FOR Travel RESULT result.

    METHODS acceptTravel FOR MODIFY
      IMPORTING keys FOR ACTION Travel~acceptTravel RESULT result.

    METHODS rejectTravel FOR MODIFY
      IMPORTING keys FOR ACTION Travel~rejectTravel RESULT result.

    METHODS deductDiscount FOR MODIFY
      IMPORTING keys FOR ACTION Travel~deductDiscount RESULT result.

    "! 인스턴스 한 건: 읽기 → factory 로 worker 생성 → execute → 저장. 오류는 failed/reported 로.
    METHODS run_action
      IMPORTING action   TYPE zif_trv_action=>ty_action
                key      TYPE ty_key
                param    TYPE any OPTIONAL
      CHANGING  failed   TYPE ty_failed
                reported TYPE ty_reported.

    METHODS read_travels
      IMPORTING keys           TYPE tt_keys
      RETURNING VALUE(travels) TYPE tt_travels.
ENDCLASS.


CLASS lhc_travel IMPLEMENTATION.

  " ---- action: 모두 같은 모양. action 식별자와 (있으면) %param 만 다르다 ----

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

  METHOD rejectTravel.
    LOOP AT keys INTO FINAL(key).
      run_action( EXPORTING action   = zif_trv_action=>reject_travel
                            key      = CORRESPONDING #( key )
                  CHANGING  failed   = failed
                            reported = reported ).
    ENDLOOP.

    result = VALUE #( FOR travel IN read_travels( CORRESPONDING #( keys ) )
                      ( %tky = travel-%tky  %param = travel ) ).
  ENDMETHOD.

  METHOD deductDiscount.
    LOOP AT keys INTO FINAL(key).
      run_action( EXPORTING action   = zif_trv_action=>deduct_discount
                            key      = CORRESPONDING #( key )
                            param    = key-%param
                  CHANGING  failed   = failed
                            reported = reported ).
    ENDLOOP.

    result = VALUE #( FOR travel IN read_travels( CORRESPONDING #( keys ) )
                      ( %tky = travel-%tky  %param = travel ) ).
  ENDMETHOD.

  " ---- 공통 ----

  METHOD run_action.
    FINAL(travels) = read_travels( VALUE #( ( key ) ) ).

    IF travels IS INITIAL.
      APPEND VALUE #( %tky        = key-%tky
                      %fail-cause = if_abap_behv=>cause-not_found ) TO failed-travel.
      RETURN.
    ENDIF.

    TRY.
        FINAL(changes) = zcl_trv_action_factory=>create( action )->execute( travel = travels[ 1 ]
                                                                            param  = param ).
      CATCH zcx_trv_action INTO FINAL(error).
        APPEND VALUE #( %tky = key-%tky ) TO failed-travel.
        APPEND VALUE #( %tky = key-%tky
                        %msg = new_message_with_text( severity = if_abap_behv_message=>severity-error
                                                      text     = error->get_text( ) ) ) TO reported-travel.
        RETURN.
    ENDTRY.

    MODIFY ENTITIES OF zi_travel IN LOCAL MODE
      ENTITY Travel
        UPDATE FROM VALUE #( ( changes ) )
      FAILED   FINAL(update_failed)
      REPORTED FINAL(update_reported).

    APPEND LINES OF update_failed-travel   TO failed-travel.
    APPEND LINES OF update_reported-travel TO reported-travel.
  ENDMETHOD.

  METHOD read_travels.
    READ ENTITIES OF zi_travel IN LOCAL MODE
      ENTITY Travel
        ALL FIELDS WITH keys
      RESULT travels.
  ENDMETHOD.

  METHOD get_instance_authorizations.
    " TODO: 실제 권한 검사로 교체. 골격에서는 전부 허용.
    result = VALUE #( FOR key IN keys
                      ( %tky                   = key-%tky
                        %update                = if_abap_behv=>auth-allowed
                        %delete                = if_abap_behv=>auth-allowed
                        %action-acceptTravel   = if_abap_behv=>auth-allowed
                        %action-rejectTravel   = if_abap_behv=>auth-allowed
                        %action-deductDiscount = if_abap_behv=>auth-allowed ) ).
  ENDMETHOD.

ENDCLASS.
