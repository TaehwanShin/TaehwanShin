"! <p class="shorttext synchronized">Travel action 예외 겸 RAP 메시지</p>
"! worker 안에서 RAISE 하면 base 클래스가 잡아서 failed/reported 의 %msg 로 넣는다.
"! 메시지 클래스: ZTRV_ACTION
CLASS zcx_trv_action DEFINITION
  PUBLIC
  INHERITING FROM cx_static_check
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
    INTERFACES if_abap_behv_message.
    INTERFACES if_t100_dyn_msg.
    INTERFACES if_t100_message.

    CONSTANTS:
      "! Travel &1: status change from &2 to &3 is not allowed
      BEGIN OF status_not_allowed,
        msgid TYPE symsgid      VALUE 'ZTRV_ACTION',
        msgno TYPE symsgno      VALUE '001',
        attr1 TYPE scx_attrname VALUE 'MV_ATTR1',
        attr2 TYPE scx_attrname VALUE 'MV_ATTR2',
        attr3 TYPE scx_attrname VALUE 'MV_ATTR3',
        attr4 TYPE scx_attrname VALUE '',
      END OF status_not_allowed,
      "! Travel &1: discount &2 % is invalid (allowed 1-100)
      BEGIN OF invalid_discount,
        msgid TYPE symsgid      VALUE 'ZTRV_ACTION',
        msgno TYPE symsgno      VALUE '002',
        attr1 TYPE scx_attrname VALUE 'MV_ATTR1',
        attr2 TYPE scx_attrname VALUE 'MV_ATTR2',
        attr3 TYPE scx_attrname VALUE '',
        attr4 TYPE scx_attrname VALUE '',
      END OF invalid_discount,
      "! No worker registered for action &1
      BEGIN OF no_worker,
        msgid TYPE symsgid      VALUE 'ZTRV_ACTION',
        msgno TYPE symsgno      VALUE '003',
        attr1 TYPE scx_attrname VALUE 'MV_ATTR1',
        attr2 TYPE scx_attrname VALUE '',
        attr3 TYPE scx_attrname VALUE '',
        attr4 TYPE scx_attrname VALUE '',
      END OF no_worker,
      "! Worker class &1 could not be instantiated
      BEGIN OF worker_not_creatable,
        msgid TYPE symsgid      VALUE 'ZTRV_ACTION',
        msgno TYPE symsgno      VALUE '004',
        attr1 TYPE scx_attrname VALUE 'MV_ATTR1',
        attr2 TYPE scx_attrname VALUE '',
        attr3 TYPE scx_attrname VALUE '',
        attr4 TYPE scx_attrname VALUE '',
      END OF worker_not_creatable,
      "! Travel &1: discount is not allowed in status &2
      BEGIN OF discount_not_allowed,
        msgid TYPE symsgid      VALUE 'ZTRV_ACTION',
        msgno TYPE symsgno      VALUE '005',
        attr1 TYPE scx_attrname VALUE 'MV_ATTR1',
        attr2 TYPE scx_attrname VALUE 'MV_ATTR2',
        attr3 TYPE scx_attrname VALUE '',
        attr4 TYPE scx_attrname VALUE '',
      END OF discount_not_allowed.

    DATA mv_attr1 TYPE string READ-ONLY.
    DATA mv_attr2 TYPE string READ-ONLY.
    DATA mv_attr3 TYPE string READ-ONLY.

    METHODS constructor
      IMPORTING textid   LIKE if_t100_message=>t100key OPTIONAL
                previous LIKE previous OPTIONAL
                severity TYPE if_abap_behv_message=>t_severity DEFAULT if_abap_behv_message=>severity-error
                mv_attr1 TYPE string OPTIONAL
                mv_attr2 TYPE string OPTIONAL
                mv_attr3 TYPE string OPTIONAL.

  PROTECTED SECTION.
  PRIVATE SECTION.
ENDCLASS.


CLASS zcx_trv_action IMPLEMENTATION.

  METHOD constructor ##ADT_SUPPRESS_GENERATION.
    super->constructor( previous = previous ).

    me->mv_attr1 = mv_attr1.
    me->mv_attr2 = mv_attr2.
    me->mv_attr3 = mv_attr3.

    CLEAR me->textid.
    IF textid IS INITIAL.
      if_t100_message~t100key = if_t100_message~default_textid.
    ELSE.
      if_t100_message~t100key = textid.
    ENDIF.

    if_abap_behv_message~m_severity = severity.
    if_t100_dyn_msg~msgty = SWITCH #( severity
                                      WHEN if_abap_behv_message=>severity-error       THEN 'E'
                                      WHEN if_abap_behv_message=>severity-warning     THEN 'W'
                                      WHEN if_abap_behv_message=>severity-information THEN 'I'
                                      WHEN if_abap_behv_message=>severity-success     THEN 'S'
                                      ELSE 'E' ).
  ENDMETHOD.

ENDCLASS.
