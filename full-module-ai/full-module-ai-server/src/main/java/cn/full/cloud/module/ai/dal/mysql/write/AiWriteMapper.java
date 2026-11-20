package cn.full.cloud.module.ai.dal.mysql.write;

import cn.full.cloud.framework.common.pojo.PageResult;
import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.ai.controller.admin.write.vo.AiWritePageReqVO;
import cn.full.cloud.module.ai.dal.dataobject.write.AiWriteDO;
import org.apache.ibatis.annotations.Mapper;

/**
 * AI 写作 Mapper
 *
 * @author xiaoxin
 */
@Mapper
public interface AiWriteMapper extends BaseMapperX<AiWriteDO> {

    default PageResult<AiWriteDO> selectPage(AiWritePageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<AiWriteDO>()
                .eqIfPresent(AiWriteDO::getUserId, reqVO.getUserId())
                .eqIfPresent(AiWriteDO::getType, reqVO.getType())
                .eqIfPresent(AiWriteDO::getPlatform, reqVO.getPlatform())
                .betweenIfPresent(AiWriteDO::getCreateTime, reqVO.getCreateTime())
                .orderByDesc(AiWriteDO::getId));
    }

}
