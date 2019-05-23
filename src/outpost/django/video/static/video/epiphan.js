$(document).ready(function() {
  $('#channels .channel').each(function(idx, elem) {
    var url = $(elem).data('url');
    var status = $(elem).find('.status');
    var start = $($.templates('#tmpl-channel-start').render());
    var stop = $($.templates('#tmpl-channel-stop').render());
    start.hide();
    stop.hide();
    status.append(start);
    status.append(stop);
    start.on('click', function() {
      start.prop('disabled', true);
      $.ajax(
        url,
        {
          method: 'START',
          dataType: 'json'
        }
      );
    });
    stop.on('click', function() {
      stop.prop('disabled', true);
      $.ajax(
        url,
        {
          method: 'STOP',
          dataType: 'json'
        }
      );
    });

    var refresh = function(){
      $.ajax(
        url,
        {
          method: 'GET',
          dataType: 'json'
        }
      ).done(function(data) {
        if (data.recording) {
          $(elem).addClass('success');
          start.hide();
          stop.show();
        } else {
          $(elem).removeClass('success');
          start.show();
          stop.hide();
        }
        start.prop('disabled', false);
        stop.prop('disabled', false);
      });
    };

    refresh();
    setInterval(refresh, 4000);
  });

  var $notification = $('#notification')
  var notification = undefined;
  $.ajax({
    method: 'GET',
    url: $notification.data('url') + '?object_id=' + $notification.data('pk') + '&content_type=' + $notification.data('ct'),
    dataType: 'json'
  }).done(function(msg) {
    console.log(msg);
    if (msg.count > 0) {
      notification  = msg.results.shift().id;
      $notification.addClass('btn-success');
      $notification.find('span.glyphicon').addClass('glyphicon-check');
    } else {
      $notification.addClass('btn-default');
      $notification.find('span.glyphicon').addClass('glyphicon-unchecked');
    }
    $notification.on('click', function() {
      $notification.attr('disabled', true);
      if (notification) {
        $.ajax({
          method: 'DELETE',
          url: $notification.data('url') + notification + '/',
          dataType: 'json'
        }).done(function(msg) {
          $notification.removeClass('btn-success').addClass('btn-default');
          $notification.find('span.glyphicon').removeClass('glyphicon-check').addClass('glyphicon-unchecked');
          notification = undefined;
          $notification.attr('disabled', false);
        });
      } else {
        $.ajax({
          method: 'POST',
          url: $notification.data('url'),
          dataType: 'json',
          data: {
            object_id: $notification.data('pk'),
            content_type: $notification.data('ct')
          }
        }).done(function(msg) {
          $notification.removeClass('btn-default').addClass('btn-success');
          $notification.find('span.glyphicon').removeClass('glyphicon-unchecked').addClass('glyphicon-check');
          notification = msg.id;
          $notification.attr('disabled', false);
        });
      }
    });
    $notification.removeClass('hidden');
  });

  $('#sources .source').each(function(idx, elem) {
    var $elem = $(elem);
    var $caption = $elem.find('.caption');
    $.ajax({
      method: 'GET',
      url: '/v1/video/epiphansource/' + $elem.data('pk') + '/',
      dataType: 'json'
    }).done(function(msg) {
      if (!msg.audio) {
        return;
      }
      var extractLevel = function(frame) {
        return Math.abs(parseFloat(frame.tags['lavfi.astats.Overall.RMS_level']));
      };
      var height = 100;
      var width = Math.floor($caption.width());
      var levels = msg.audio.frames.map(extractLevel);
      var multiplier = height / levels.reduce(function(a, b) { return Math.max(a, b); });
      var w = width / levels.length;
      d3.selectAll($caption.toArray())
        .append('svg')
        .attr('width', width)
        .attr('height', height)
        .selectAll('circle')
        .data(levels)
        .enter()
        .append('rect')
        .attr('x', function(d, i) {
          return i * w;
        })
        .attr('y', function(d, i) {
          return height - (multiplier * d);
        })
        .attr('width', w)
        .attr('height', function(d) {
          return multiplier * d;
        });
    });
  });

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
