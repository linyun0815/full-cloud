package cn.full.cloud.module.iot.controller.admin.ota.vo.task.record;

import cn.full.cloud.framework.common.pojo.PageParam;
import cn.full.cloud.framework.common.validation.InEnum;
import cn.full.cloud.module.iot.enums.ota.IotOtaTaskRecordStatusEnum;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Schema(description = "管理后台 - IoT OTA 升级记录分页 Request VO")
@Data
public class IotOtaTaskRecordPageReqVO extends PageParam {

    @Schema(description = "升级任务编号", example = "1024")
    private Long taskId;

    @Schema(description = "升级记录状态", example = "5")
    @InEnum(IotOtaTaskRecordStatusEnum.class)
    private Integer status;

}
