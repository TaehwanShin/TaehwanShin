"! <p class="shorttext synchronized">Travel action worker 추상 베이스 (템플릿 메서드)</p>
"! execute 가 공통 흐름을 고정한다:
"!   1. 키 변환 + on_prepare (worker 가 action 별 typed keys 를 보관할 기회)
"!   2. 게이트웨이로 인스턴스 읽기, 없는 키는 not_found 로 failed
"!   3. 인스턴스마다 check_precondition → process (예외는 failed/reported 로 변환)
"!   4. 게이트웨이로 UPDATE
"!   5. 성공한 인스턴스를 다시 읽어 result ($self) 채우기
"! 구체 worker 는 process 만 필수로 구현하고, 필요하면 check_precondition / on_prepare / on_after_update 를 재정의한다.
"! worker 인스턴스는 호출마다 새로 만들어지므로(factory) 호출 범위의 상태를 멤버에 둬도 된다.
CLASS zcl_trv_action_base DEFINITION
  PUBLIC
  ABSTRACT
  CREATE PUBLIC.

  PUBLIC SECTION.
    INTERFACES zif_trv_action.
    ALIASES execute FOR zif_trv_action~execute.

  PROTECTED SECTION.
    TYPES ts_travel        TYPE STRUCTURE FOR READ RESULT zi_travel\\Travel.
    TYPES ts_travel_update TYPE STRUCTURE FOR UPDATE      zi_travel\\Travel.

    "! execute 가 주입받은 게이트웨이. worker 가 추가로 읽을 것이 있으면 사용한다.
    DATA mo_gateway TYPE REF TO zif_trv_bo_gateway.

    "! 훅: 인스턴스를 읽기 전에 호출. 파라미터 action 은 여기서 typed keys 를 보관한다.
    METHODS on_prepare
      IMPORTING it_keys TYPE ANY TABLE.

    "! 훅: 인스턴스별 사전조건. 실패면 메시지 객체를 돌려준다(initial = 통과).
    METHODS check_precondition
      IMPORTING is_travel         TYPE ts_travel
      RETURNING VALUE(ro_message) TYPE REF TO if_abap_behv_message.

    "! 필수: 변경할 필드 값을 cs_update 에 넣고 해당 %control 을 켠다.
    "! 비즈니스 오류는 zcx_trv_action 으로 RAISE 하면 base 가 failed/reported 로 바꾼다.
    METHODS process ABSTRACT
      IMPORTING is_travel TYPE ts_travel
      CHANGING  cs_update TYPE ts_travel_update
      RAISING   zcx_trv_action.

    "! 훅: UPDATE 가 끝난 뒤 호출(성공 인스턴스 목록). 후속 처리/이벤트 발행 등에 사용.
    METHODS on_after_update
      IMPORTING it_travels TYPE zif_trv_bo_gateway=>tt_travel.

  PRIVATE SECTION.
    METHODS add_failed
      IMPORTING is_travel   TYPE ts_travel
                io_message  TYPE REF TO if_abap_behv_message
      CHANGING  cs_failed   TYPE zif_trv_bo_gateway=>ts_failed
                cs_reported TYPE zif_trv_bo_gateway=>ts_reported.

    METHODS fill_result
      IMPORTING it_travels TYPE zif_trv_bo_gateway=>tt_travel
      CHANGING  ct_result  TYPE ANY TABLE.
ENDCLASS.


CLASS zcl_trv_action_base IMPLEMENTATION.

  METHOD zif_trv_action~execute.
    DATA lt_read_keys TYPE zif_trv_bo_gateway=>tt_travel_key.
    DATA lt_updates   TYPE zif_trv_bo_gateway=>tt_travel_update.

    mo_gateway = io_gateway.

    " 1. action 별 키 타입 → BO 공통 읽기 키 타입. %tky 는 모든 파생 타입에 공통이다.
    MOVE-CORRESPONDING it_keys TO lt_read_keys.
    on_prepare( it_keys ).

    " 2. 인스턴스 읽기. 없는 키는 not_found 로 실패 처리.
    DATA(lt_travels) = mo_gateway->read_travels( lt_read_keys ).

    LOOP AT lt_read_keys INTO DATA(ls_read_key).
      IF NOT line_exists( lt_travels[ %tky = ls_read_key-%tky ] ).
        APPEND VALUE #( %tky        = ls_read_key-%tky
                        %fail-cause = if_abap_behv=>cause-not_found ) TO cs_failed-travel.
      ENDIF.
    ENDLOOP.

    " 3. 인스턴스별 사전조건 + 처리
    LOOP AT lt_travels ASSIGNING FIELD-SYMBOL(<ls_travel>).
      DATA(lo_message) = check_precondition( <ls_travel> ).
      IF lo_message IS BOUND.
        add_failed( EXPORTING is_travel   = <ls_travel>
                              io_message  = lo_message
                    CHANGING  cs_failed   = cs_failed
                              cs_reported = cs_reported ).
        CONTINUE.
      ENDIF.

      DATA(ls_update) = VALUE ts_travel_update( %tky = <ls_travel>-%tky ).
      TRY.
          process( EXPORTING is_travel = <ls_travel>
                   CHANGING  cs_update = ls_update ).
          APPEND ls_update TO lt_updates.
        CATCH zcx_trv_action INTO DATA(lx_action).
          add_failed( EXPORTING is_travel   = <ls_travel>
                                io_message  = lx_action
                      CHANGING  cs_failed   = cs_failed
                                cs_reported = cs_reported ).
      ENDTRY.
    ENDLOOP.

    " 4. 변경 반영
    IF lt_updates IS NOT INITIAL.
      mo_gateway->update_travels( EXPORTING it_updates  = lt_updates
                                  CHANGING  cs_failed   = cs_failed
                                            cs_reported = cs_reported ).
    ENDIF.

    " 5. 실패하지 않은 인스턴스만 다시 읽어 result 로 반환
    DATA(lt_result_keys) = lt_read_keys.
    LOOP AT cs_failed-travel INTO DATA(ls_failed).
      DELETE lt_result_keys WHERE %tky = ls_failed-%tky.
    ENDLOOP.

    DATA(lt_result_travels) = mo_gateway->read_travels( lt_result_keys ).
    on_after_update( lt_result_travels ).
    fill_result( EXPORTING it_travels = lt_result_travels
                 CHANGING  ct_result  = ct_result ).
  ENDMETHOD.

  METHOD on_prepare.
    " 기본: 아무것도 하지 않음. 파라미터 action 이 재정의한다.
  ENDMETHOD.

  METHOD check_precondition.
    " 기본: 항상 통과. 필요한 worker 가 재정의한다.
    CLEAR ro_message.
  ENDMETHOD.

  METHOD on_after_update.
    " 기본: 아무것도 하지 않음.
  ENDMETHOD.

  METHOD add_failed.
    APPEND VALUE #( %tky        = is_travel-%tky
                    %fail-cause = if_abap_behv=>cause-unspecific ) TO cs_failed-travel.
    APPEND VALUE #( %tky = is_travel-%tky
                    %msg = io_message ) TO cs_reported-travel.
  ENDMETHOD.

  METHOD fill_result.
    " result 타입은 action 마다 다르지만(TABLE FOR ACTION RESULT zi_travel~<action>)
    " $self 결과는 항상 %tky + %param(= 엔티티 구조) 이므로 컴포넌트 이름으로 동적으로 채운다.
    CLEAR ct_result.
    LOOP AT it_travels INTO DATA(ls_travel).
      INSERT INITIAL LINE INTO TABLE ct_result ASSIGNING FIELD-SYMBOL(<ls_result>).
      ASSIGN COMPONENT '%TKY'   OF STRUCTURE <ls_result> TO FIELD-SYMBOL(<ls_tky>).
      ASSIGN COMPONENT '%PARAM' OF STRUCTURE <ls_result> TO FIELD-SYMBOL(<ls_param>).
      <ls_tky>   = ls_travel-%tky.
      <ls_param> = CORRESPONDING #( ls_travel ).
    ENDLOOP.
  ENDMETHOD.

ENDCLASS.
