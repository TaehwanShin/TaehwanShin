"! <p class="shorttext synchronized">Travel action worker 팩토리</p>
"! action 이름 → worker 클래스 레지스트리. 호출마다 새 worker 인스턴스를 만든다
"! (worker 가 호출 범위의 상태를 멤버에 보관하므로 재사용하지 않는다).
"! 테스트에서는 inject 로 test double 을 끼워 넣고, teardown 에서 reset 한다.
CLASS zcl_trv_action_factory DEFINITION
  PUBLIC
  FINAL
  CREATE PRIVATE.

  PUBLIC SECTION.
    CLASS-METHODS get_instance
      RETURNING VALUE(ro_factory) TYPE REF TO zcl_trv_action_factory.

    "! action 에 등록된 worker 의 새 인스턴스를 돌려준다.
    "! @raising zcx_trv_action | 미등록 action 이거나 클래스를 생성할 수 없을 때
    METHODS create
      IMPORTING iv_action        TYPE string
      RETURNING VALUE(ro_worker) TYPE REF TO zif_trv_action
      RAISING   zcx_trv_action.

    "! action 에 worker 클래스를 (재)등록한다. 체이닝 가능.
    METHODS register
      IMPORTING iv_action         TYPE string
                iv_class          TYPE seoclsname
      RETURNING VALUE(ro_factory) TYPE REF TO zcl_trv_action_factory.

    "! 테스트 전용: 이 action 에는 항상 io_worker 를 돌려준다.
    METHODS inject
      IMPORTING iv_action TYPE string
                io_worker TYPE REF TO zif_trv_action.

    "! 레지스트리를 기본 상태로 되돌린다(주입 해제 포함).
    METHODS reset.

    "! 등록된 action 이름 목록 (디버깅/문서화용)
    METHODS get_registered_actions
      RETURNING VALUE(rt_actions) TYPE string_table.

  PROTECTED SECTION.
  PRIVATE SECTION.
    TYPES:
      BEGIN OF ts_registry,
        action TYPE string,
        class  TYPE seoclsname,
        worker TYPE REF TO zif_trv_action,   " bound 이면 주입된 double
      END OF ts_registry.
    TYPES tt_registry TYPE HASHED TABLE OF ts_registry WITH UNIQUE KEY action.

    CLASS-DATA go_instance TYPE REF TO zcl_trv_action_factory.

    DATA mt_registry TYPE tt_registry.

    METHODS constructor.
    METHODS register_defaults.
ENDCLASS.


CLASS zcl_trv_action_factory IMPLEMENTATION.

  METHOD get_instance.
    IF go_instance IS NOT BOUND.
      go_instance = NEW #( ).
    ENDIF.
    ro_factory = go_instance.
  ENDMETHOD.

  METHOD constructor.
    register_defaults( ).
  ENDMETHOD.

  METHOD register_defaults.
    " 새 action 을 추가하면 여기에 한 줄 등록한다.
    register( iv_action = zif_trv_action=>c_action-accept_travel   iv_class = 'ZCL_TRV_ACTION_ACCEPT'
    )->register( iv_action = zif_trv_action=>c_action-reject_travel   iv_class = 'ZCL_TRV_ACTION_REJECT'
    )->register( iv_action = zif_trv_action=>c_action-reopen_travel   iv_class = 'ZCL_TRV_ACTION_REOPEN'
    )->register( iv_action = zif_trv_action=>c_action-deduct_discount iv_class = 'ZCL_TRV_ACTION_DEDUCT_DISC' ).
  ENDMETHOD.

  METHOD register.
    DATA(ls_entry) = VALUE ts_registry( action = to_upper( iv_action )
                                        class  = to_upper( iv_class ) ).
    DELETE mt_registry WHERE action = ls_entry-action.
    INSERT ls_entry INTO TABLE mt_registry.
    ro_factory = me.
  ENDMETHOD.

  METHOD inject.
    DATA(lv_action) = to_upper( iv_action ).
    ASSIGN mt_registry[ action = lv_action ] TO FIELD-SYMBOL(<ls_entry>).
    IF sy-subrc <> 0.
      INSERT VALUE ts_registry( action = lv_action ) INTO TABLE mt_registry ASSIGNING <ls_entry>.
    ENDIF.
    <ls_entry>-worker = io_worker.
  ENDMETHOD.

  METHOD reset.
    CLEAR mt_registry.
    register_defaults( ).
  ENDMETHOD.

  METHOD get_registered_actions.
    rt_actions = VALUE #( FOR ls_entry IN mt_registry ( ls_entry-action ) ).
    SORT rt_actions.
  ENDMETHOD.

  METHOD create.
    DATA(lv_action) = to_upper( iv_action ).

    ASSIGN mt_registry[ action = lv_action ] TO FIELD-SYMBOL(<ls_entry>).
    IF sy-subrc <> 0.
      RAISE EXCEPTION NEW zcx_trv_action( textid   = zcx_trv_action=>no_worker
                                           mv_attr1 = lv_action ).
    ENDIF.

    " 테스트 double 이 주입되어 있으면 그대로 반환
    IF <ls_entry>-worker IS BOUND.
      ro_worker = <ls_entry>-worker.
      RETURN.
    ENDIF.

    TRY.
        CREATE OBJECT ro_worker TYPE (<ls_entry>-class).
      CATCH cx_sy_create_object_error cx_sy_move_cast_error INTO DATA(lx_create).
        RAISE EXCEPTION NEW zcx_trv_action( textid   = zcx_trv_action=>worker_not_creatable
                                             mv_attr1 = |{ <ls_entry>-class }|
                                             previous = lx_create ).
    ENDTRY.
  ENDMETHOD.

ENDCLASS.
