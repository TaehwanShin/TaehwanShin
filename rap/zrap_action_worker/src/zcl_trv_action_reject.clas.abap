"! <p class="shorttext synchronized">Worker: rejectTravel</p>
CLASS zcl_trv_action_reject DEFINITION
  PUBLIC
  INHERITING FROM zcl_trv_action_status_base
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
  PROTECTED SECTION.
    METHODS get_target_status REDEFINITION.
  PRIVATE SECTION.
ENDCLASS.


CLASS zcl_trv_action_reject IMPLEMENTATION.

  METHOD get_target_status.
    rv_status = zcl_trv_status_rules=>c_status-rejected.
  ENDMETHOD.

ENDCLASS.
