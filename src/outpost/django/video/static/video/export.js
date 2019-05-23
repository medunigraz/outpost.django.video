$(document).ready(function() {
    var alert = $('#alert');
    $('.exporter').each(function(index, exporter) {
        var url = $(exporter).data('url');
        var request = $(exporter).find('.request');
        var download = $(exporter).find('.download');
        var status = $(exporter).find('.status');
        var bar = status.find('.progress-bar');
        var percent = status.find('.percent');
        var action = status.find('.action');
        request.click(function(evt) {
            download.addClass('disabled');
            request.addClass('hidden');
            download.removeClass('hidden');
            var queue = $.ajax({
                url: url,
                method: 'POST'
            });
            queue.done(function(data) {
                bar.css('width', '0%').attr('aria-valuenow', 0);
                status.removeClass('hidden');
                var task = checkTaskProgress(data.task)
                task.progress(function(data) {
                    var done = data.info.current / data.info.maximum * 100;
                    bar.css('width', done + '%').attr('aria-valuenow', done);
                    percent.text(Number((done).toFixed(1)))
                    action.text(data.info.action)
                });
                task.done(function(data) {
                    download.attr('href', data.info);
                    download.removeClass('disabled');
                    status.addClass('hidden');
                });
                task.fail(function(data) {
                    var message = alert.clone();
                    message.find('.message').text(data.info);
                    alert.after(message);
                    message.removeClass('hidden');
                    status.addClass('hidden');
                    download.addClass('hidden');
                    request.removeClass('disabled');
                    request.removeClass('hidden');
                });
            });
        })
    });
});
