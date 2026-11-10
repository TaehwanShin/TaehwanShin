"! <p class="shorttext synchronized">Worker: reopenTravel</p>
CLASS zcl_trv_action_reopen DEFINITION
  PUBLIC
  INHERITING FROM zcl_trv_action_status_base
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
  PROTECTED SECTION.
    METHODS get_target_status REDEFINITION.
  PRIVATE SECTION.
ENDCLASS.


CLASS zcl_trv_action_reopen IMPLEMENTATION.

  METHOD get_target_status.
    rv_status = zcl_trv_status_rules=>c_status-open.
  ENDMETHOD.

ENDCLASS.
