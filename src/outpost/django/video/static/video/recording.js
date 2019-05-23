$(document).ready(function() {
  $('#recordings tbody tr').each(function(idx, elem) {
    var $entry = $(elem);
    var url = $entry.data('url');
    var $delete = $entry.find('button.delete');
    $delete.confirm(
      '',
      $.templates('#tmpl-confirm-delete').render(),
      function() {
        $delete.prop('disabled', true);
        $.ajax(
          url,
          {
            method: 'DELETE',
            dataType: 'json'
          }
        ).done(function() {
          $entry.remove();
        }).fail(function() {
          $delete.prop('disabled', false);
        });
      }
    );
  });
});
